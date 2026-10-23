"""The Claude wiring: what each call asks for, how it is priced, and declined requests."""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from backedcv.llm import structured
from backedcv.llm.prompt_loader import Prompt
from backedcv.llm.structured import MAX_TOKENS, AnthropicStructuredLLM, LLMError, usage_record
from backedcv.settings import Settings

PROMPT = Prompt(id="verify", version="1", tier="fast", text="Check the claim.")
MODEL = "claude-haiku-5-5"


class Answer(BaseModel):
    label: str


class RefusingModel:
    """Stands in for ChatAnthropic and its structured runnable: every answer is a refusal."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, **_options) -> "RefusingModel":
        return self

    def with_structured_output(self, schema, **_options) -> "RefusingModel":
        return self

    async def ainvoke(self, messages, config=None) -> dict:
        self.calls += 1
        raw = AIMessage(content="", response_metadata={"stop_reason": "refusal"})
        return {"raw": raw, "parsed": None, "parsing_error": "no answer"}


def _llm(tmp_path) -> AnthropicStructuredLLM:
    settings = Settings(data_dir=tmp_path, model_fast=MODEL, model_strong=MODEL)
    return AnthropicStructuredLLM(settings, cache=False)


def test_each_call_sets_its_effort_and_no_sampling_parameters(tmp_path):
    chat = _llm(tmp_path)._chat("fast", "verify")

    assert chat.model == MODEL
    assert chat.reasoning_effort == "high"  # models.toml: the verifier thinks the most
    assert chat.max_tokens == MAX_TOKENS
    assert chat.temperature is None  # Claude Haiku 5.5 rejects sampling parameters


@pytest.mark.parametrize(("tokens_in", "cost"), [(100_000, 0.0105), (200_000, 0.1025)])
def test_a_prompt_over_100k_tokens_is_priced_at_the_long_rates(tokens_in, cost):
    usage = {"input_tokens": tokens_in, "output_tokens": 1_000, "total_tokens": tokens_in + 1_000}

    record = usage_record("match_chunk", MODEL, AIMessage(content="{}", usage_metadata=usage))

    assert record["cost_usd"] == pytest.approx(cost)


def test_a_declined_request_is_not_repaired(tmp_path, monkeypatch):
    model = RefusingModel()
    monkeypatch.setattr(structured, "ChatAnthropic", model.chat)

    with pytest.raises(LLMError, match="declined"):
        asyncio.run(_llm(tmp_path).run(PROMPT, "the claim", Answer, node="verify_batch"))

    assert model.calls == 1
