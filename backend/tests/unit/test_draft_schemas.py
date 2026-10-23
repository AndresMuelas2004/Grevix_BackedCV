"""Draft schemas: every field required, nullable when optional, no free-form dicts."""

import pytest
from pydantic import BaseModel

from backedcv.llm import drafts

SCHEMAS = [drafts.CVStructureDraft, drafts.JobExtractionDraft, drafts.MatchChunkDraft]


def _objects(schema: dict):
    defs = schema.get("$defs", {})
    yield schema
    yield from defs.values()


@pytest.mark.parametrize("model", SCHEMAS)
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
