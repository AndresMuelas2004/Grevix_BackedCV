"""One interface for every structured LLM call, so tests can swap in canned answers."""

import logging
from typing import Literal, Protocol, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from backedcv.config import load
from backedcv.domain.text import normalize_text
from backedcv.llm.cache import LLMCache, answer_key
from backedcv.llm.prompt_loader import Prompt
from backedcv.settings import Settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Tier = Literal["fast", "strong"]
# Room for the model's thinking plus the longest answer. It also keeps calls non-streaming: the SDK
# refuses a non-streaming call whose max_tokens could take more than 10 minutes.
MAX_TOKENS = 16_000


class LLMError(Exception):
    """The model could not produce a valid answer (after one repair attempt)."""


class StructuredLLM(Protocol):
    async def run(
        self, prompt: Prompt, data: str, schema: type[T], *, node: str
    ) -> tuple[T, dict]: ...


def usage_record(node: str, model: str, message: AIMessage | None) -> dict:
    meta = (message.usage_metadata if message is not None else None) or {}
    tokens_in, tokens_out = meta.get("input_tokens", 0), meta.get("output_tokens", 0)
    price = load("models").get("prices", {}).get(model, {})
    threshold = price.get("long_prompt_tokens")
    long_prompt = threshold is not None and tokens_in > threshold
    if long_prompt:
        log.warning("%s: a %d-token prompt is billed at the long-prompt rates", node, tokens_in)
    rate_in = price.get("long_input" if long_prompt else "input", 0)
    rate_out = price.get("long_output" if long_prompt else "output", 0)
    cost = (tokens_in * rate_in + tokens_out * rate_out) / 1_000_000
    return {
        "node": node,
        "model": model,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "cost_usd": round(cost, 6),
        "cached": False,
    }


class AnthropicStructuredLLM:
    def __init__(self, settings: Settings, cache: bool | None = None):
        """`cache` overrides `settings.llm_cache` when it is given (the evals pass False)."""
        self.settings = settings
        enabled = settings.llm_cache if cache is None else cache
        self.cache = LLMCache(settings.data_dir / "llm_cache.sqlite") if enabled else None

    def _model_name(self, tier: str) -> str:
        return self.settings.model_strong if tier == "strong" else self.settings.model_fast

    def _effort(self, prompt_id: str) -> str:
        return load("models").get("effort", {}).get(prompt_id, "low")

    def _chat(self, tier: str, prompt_id: str) -> ChatAnthropic:
        # No temperature and no seed on purpose: Claude Haiku 5.5 rejects sampling parameters, and
        # the Messages API has no seed. Thinking is adaptive (on by default) and the effort level
        # sets how much the model thinks. Stability comes from the canonical input, the answer
        # cache, the extraction rules and the code after the model.
        return ChatAnthropic(
            model=self._model_name(tier),
            max_tokens=MAX_TOKENS,
            max_retries=1,
            effort=self._effort(prompt_id),
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
        model = self._model_name(prompt.tier)
        chat = self._chat(prompt.tier, prompt.id)
        # Claude's structured outputs: the answer is constrained to the schema's JSON.
        runnable = chat.with_structured_output(schema, method="json_schema", include_raw=True)
        messages = [SystemMessage(prompt.text), HumanMessage(data)]
        config = {"run_name": node, "metadata": prompt.metadata, "tags": [prompt.id]}

        result = await runnable.ainvoke(messages, config=config)
        usage = usage_record(node, model, result.get("raw"))
        if result.get("parsed") is not None:
            return result["parsed"], usage
        _raise_if_refused(node, result.get("raw"))

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
        retry_usage = usage_record(node, model, retry.get("raw"))
        usage = {
            **usage,
            "input_tokens": usage["input_tokens"] + retry_usage["input_tokens"],
            "output_tokens": usage["output_tokens"] + retry_usage["output_tokens"],
            "cost_usd": round(usage["cost_usd"] + retry_usage["cost_usd"], 6),
        }
        if retry.get("parsed") is None:
            raise LLMError(f"{node}: invalid structured output ({retry.get('parsing_error')})")
        return retry["parsed"], usage


def _raise_if_refused(node: str, message: AIMessage | None) -> None:
    """A request the model declined is not repaired: the same input would be declined again."""
    if message is not None and message.response_metadata.get("stop_reason") == "refusal":
        raise LLMError(f"{node}: the model declined the request")
