"""Graph state: plain JSON-friendly dicts, so checkpoints never hold custom classes or bytes."""

import operator
from typing import Annotated, TypedDict


def merge_by_id(left: dict | None, right: dict | None) -> dict:
    """Parallel branches each add their own keys (requirement or suggestion IDs)."""
    return {**(left or {}), **(right or {})}


class AnalysisState(TypedDict, total=False):
    # Inputs
    analysis_id: str
    created_at: str
    cv_meta: dict  # kind, filename, size: never the bytes
    cv_lines: list[dict]
    job_text: str
    facts: dict
    excluded_ids: list[str]
    included_flagged_ids: list[str]

    # Analysis
    cv: dict
    job: dict
    job_notes: list[str]
    flags: list[dict]
    banners: list[dict]
    assessment_drafts: Annotated[dict, merge_by_id]
    assessments: dict
    score: dict
    verdict: dict

    # Bookkeeping
    errors: Annotated[list, operator.add]
    usage: Annotated[list, operator.add]


class MatchTask(TypedDict):
    """Compact payload for one parallel matching call."""

    requirement_ids: list[str]
    requirements_block: str
    cv_block: str
