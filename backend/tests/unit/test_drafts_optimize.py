"""Strict-mode checks for the optimize drafts, and load checks for their prompts."""

import pytest
from pydantic import BaseModel

from backedcv.llm import drafts_optimize
from backedcv.llm.prompt_loader import load_prompt

DRAFTS = [
    drafts_optimize.SuggestionDraft,
    drafts_optimize.SuggestionsDraft,
    drafts_optimize.ClaimDraft,
    drafts_optimize.TermJudgementDraft,
    drafts_optimize.VerificationDraft,
    drafts_optimize.VerificationBatchDraft,
    drafts_optimize.ContradictionDraft,
    drafts_optimize.DoubtfulCredentialDraft,
    drafts_optimize.PostingReviewDraft,
]

# (prompt file name, version, tier, data blocks the prompt refers to)
PROMPTS = [
    ("suggest", "2", "strong", ["<cv_lines>", "<facts>", "<requirements>"]),
    ("verify", "3", "strong", ["<cv_lines>", "<facts>", "<suggestions>"]),
    ("review_posting", "1", "fast", ["<job_meta>", "<requirements>"]),
]


def _objects(schema: dict):
    defs = schema.get("$defs", {})
    yield schema
    yield from defs.values()


@pytest.mark.parametrize("model", DRAFTS)
def test_schema_is_strict_compatible(model: type[BaseModel]):
    schema = model.model_json_schema()
    for obj in _objects(schema):
        if obj.get("type") != "object":
            continue
        properties = obj.get("properties", {})
        assert set(obj.get("required", [])) == set(properties), obj.get("title")
        for name, prop in properties.items():
            assert prop.get("type") != "object" or "properties" in prop, name
            assert "additionalProperties" not in prop, name
            assert prop.get("description"), name


@pytest.mark.parametrize(("name", "version", "tier", "blocks"), PROMPTS)
def test_prompt_loads_with_id_and_data_blocks(
    name: str, version: str, tier: str, blocks: list[str]
):
    prompt = load_prompt(name)
    assert prompt.id == name
    assert prompt.version == version
    assert prompt.tier == tier
    for block in blocks:
        assert block in prompt.text, block
