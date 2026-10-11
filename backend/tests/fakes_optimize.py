"""Canned suggest and verify answers for the optimize step, on top of the analysis fakes."""

from backedcv.llm.drafts_optimize import (
    ClaimDraft,
    SuggestionDraft,
    SuggestionsDraft,
    VerificationBatchDraft,
    VerificationDraft,
)
from tests.fakes import FakeLLM

# Line IDs of tests/fakes.CV_TEXT: L007 is "Built a support bot with LangGraph". R03 ("agent
# frameworks") is met only by meaning, so it is the requirement the suggestions aim at.
FAITHFUL_REWORD = SuggestionDraft(
    kind="align_wording",
    target="L007",
    after="Built a support bot with agent frameworks (LangGraph)",
    cited_refs=["L007"],
    requirement_ids=["R03"],
    rationale="L007 shows LangGraph, which is an agent framework.",
)
INVENTED_NUMBER = SuggestionDraft(
    kind="align_wording",
    target="L007",
    after="Built a support bot with agent frameworks (LangGraph), cutting tickets by 40%",
    cited_refs=["L007"],
    requirement_ids=["R03"],
    rationale="L007 shows the support bot and LangGraph.",
)
ADD_SKILL = SuggestionDraft(
    kind="add_skill",
    target="L007",
    after="agent frameworks",
    cited_refs=["L007"],
    requirement_ids=["R03"],
    rationale="L007 shows LangGraph, which is an agent framework.",
)


def _usage(node: str) -> dict:
    return {"node": node, "model": "fake", "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0}


def _supports(row: str) -> VerificationDraft:
    """Answers one suggestion row: the whole text is one claim, backed by the cited IDs."""
    sid, cited, _introduced, after = row.split(" | ", 3)
    claim = ClaimDraft(
        text=after.removeprefix("after: "),
        supported_by=cited.removeprefix("cited: ").split(", "),
        unsupported_reason=None,
    )
    return VerificationDraft(suggestion_id=sid, claims=[claim], term_judgements=[], uncertain=False)


class FakeOptimizeLLM(FakeLLM):
    """FakeLLM that also answers suggest and verify. `inputs` keeps the data each of them got."""

    def __init__(self, suggestions: list[SuggestionDraft] | None = None):
        super().__init__()
        if suggestions is None:
            suggestions = [FAITHFUL_REWORD, INVENTED_NUMBER, ADD_SKILL]
        self.suggestions = suggestions
        self.inputs: list[tuple[str, str]] = []

    async def run(self, prompt, data, schema, *, node):
        if schema is SuggestionsDraft:
            self.calls.append(node)
            self.inputs.append((node, data))
            return SuggestionsDraft(suggestions=self.suggestions), _usage(node)
        if schema is VerificationBatchDraft:
            self.calls.append(node)
            self.inputs.append((node, data))
            rows = data.split("<suggestions>\n", 1)[1].split("\n</suggestions>", 1)[0]
            verifications = [_supports(row) for row in rows.splitlines()]
            return VerificationBatchDraft(verifications=verifications), _usage(node)
        return await super().run(prompt, data, schema, node=node)
