"""One interface for every structured LLM call, so tests can swap in canned answers."""

from typing import Literal, Protocol, TypeVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from backedcv.config import load
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
    }


class OpenAIStructuredLLM:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _model_name(self, tier: str) -> str:
        return self.settings.model_strong if tier == "strong" else self.settings.model_fast

    def _chat(self, tier: str, prompt_id: str) -> ChatOpenAI:
        effort = load("models").get("effort", {}).get(prompt_id, "low")
        return ChatOpenAI(
            model=self._model_name(tier),
            use_responses_api=True,
            store=False,
            max_retries=1,
            reasoning={"effort": effort},
        )

    async def run(self, prompt: Prompt, data: str, schema: type[T], *, node: str) -> tuple[T, dict]:
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
