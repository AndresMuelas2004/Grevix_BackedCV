"""One interface for every structured LLM call, so tests can swap in canned answers."""

from typing import Literal, Protocol, TypeVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from backedcv.config import load
from backedcv.domain.text import normalize_text
from backedcv.llm.cache import LLMCache, answer_key
from backedcv.llm.prompt_loader import Prompt
from backedcv.settings import Settings

T = TypeVar("T", bound=BaseModel)
Tier = Literal["fast", "strong"]


class LLMError(Exception):
    """The model could not produce a valid answer (after one repair attempt)."""


class StructuredLLM(Protocol):
    async def run(
        self, prompt: Prompt, data: str, schema: type[T], *, node: str
    ) -> tuple[T, dict]: ...


def usage_record(node: str, model: str, message: AIMessage | None) -> dict:
    meta = (message.usage_metadata if message is not None else None) or {}
    tokens_in, tokens_out = meta.get("input_tokens", 0), meta.get("output_tokens", 0)
    price = load("models").get("prices", {}).get(model, {"input": 0, "output": 0})
    cost = (tokens_in * price["input"] + tokens_out * price["output"]) / 1_000_000
    return {
        "node": node,
        "model": model,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "cost_usd": round(cost, 6),
        "cached": False,
    }


class OpenAIStructuredLLM:
    def __init__(self, settings: Settings, cache: bool | None = None):
        """`cache` overrides `settings.llm_cache` when it is given (the evals pass False)."""
        self.settings = settings
        enabled = settings.llm_cache if cache is None else cache
        self.cache = LLMCache(settings.data_dir / "llm_cache.sqlite") if enabled else None

    def _model_name(self, tier: str) -> str:
        return self.settings.model_strong if tier == "strong" else self.settings.model_fast

    def _effort(self, prompt_id: str) -> str:
        return load("models").get("effort", {}).get(prompt_id, "low")

    def _chat(self, tier: str, prompt_id: str) -> ChatOpenAI:
        # No temperature and no seed on purpose. Checked live on 2026-10-11: gpt-6-luna with a
        # reasoning effort answers "Unsupported parameter: 'temperature' is not supported with
        # this model", and the Responses API has no seed parameter. Stability comes from the
        # canonical input, the answer cache, the extraction rules and the code after the model.
        return ChatOpenAI(
            model=self._model_name(tier),
            use_responses_api=True,
            store=False,
            max_retries=1,
            reasoning={"effort": self._effort(prompt_id)},
        )

    async def run(self, prompt: Prompt, data: str, schema: type[T], *, node: str) -> tuple[T, dict]:
        # The model gets the canonical input the cache key is computed on (idempotent: the CV
        # and the posting are already normalized where they enter the app).
        data = normalize_text(data)
        if self.cache is None:
            return await self._ask(prompt, data, schema, node=node)
        model = self._model_name(prompt.tier)
        key = answer_key(model, self._effort(prompt.id), prompt, schema, data)
        cached = self._from_cache(key, schema, node=node, model=model)
        if cached is not None:
            return cached
        parsed, usage = await self._ask(prompt, data, schema, node=node)
        self.cache.put(
            key, parsed.model_dump(mode="json"), usage["input_tokens"], usage["output_tokens"]
        )
        return parsed, usage

    def _from_cache(
        self, key: str, schema: type[T], *, node: str, model: str
    ) -> tuple[T, dict] | None:
        """The stored answer as a zero-cost usage record, or None when there is no usable row."""
        stored = self.cache.get(key)
        if stored is None:
            return None
        answer, tokens_in, tokens_out = stored
        try:
            parsed = schema.model_validate(answer)
        except ValidationError:
            return None  # the row no longer fits the schema: the model is asked again
        usage = {
            "node": node,
            "model": model,
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "cost_usd": 0.0,
            "cached": True,
        }
        return parsed, usage

    async def _ask(
        self, prompt: Prompt, data: str, schema: type[T], *, node: str
    ) -> tuple[T, dict]:
        chat = self._chat(prompt.tier, prompt.id)
        runnable = chat.with_structured_output(
            schema, method="json_schema", strict=True, include_raw=True
        )
        messages = [SystemMessage(prompt.text), HumanMessage(data)]
        config = {"run_name": node, "metadata": prompt.metadata, "tags": [prompt.id]}

        result = await runnable.ainvoke(messages, config=config)
        usage = usage_record(node, chat.model_name, result.get("raw"))
        if result.get("parsed") is not None:
            return result["parsed"], usage

        # One repair attempt with the validation error, then give up.
        error = result.get("parsing_error")
        repair = [
            *messages,
            HumanMessage(
                f"Your previous answer was not valid for the schema: {error}. "
                "Answer again with valid output only."
            ),
        ]
        retry = await runnable.ainvoke(repair, config=config)
        retry_usage = usage_record(node, chat.model_name, retry.get("raw"))
        usage = {
            **usage,
            "input_tokens": usage["input_tokens"] + retry_usage["input_tokens"],
            "output_tokens": usage["output_tokens"] + retry_usage["output_tokens"],
            "cost_usd": round(usage["cost_usd"] + retry_usage["cost_usd"], 6),
        }
        if retry.get("parsed") is None:
            raise LLMError(f"{node}: invalid structured output ({retry.get('parsing_error')})")
        return retry["parsed"], usage
