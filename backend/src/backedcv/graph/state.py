"""Graph state: plain JSON-friendly dicts, so checkpoints never hold custom classes or bytes."""

import operator
from typing import Annotated, TypedDict


def merge_by_id(left: dict | None, right: dict | None) -> dict:
    """Parallel branches each add their own keys (requirement or suggestion IDs)."""
    return {**(left or {}), **(right or {})}


def merge_items_by_id(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    """List of records with an `id` (suggestions): a later record replaces the earlier one."""
    merged = {item["id"]: item for item in left or []}
    merged.update({item["id"]: item for item in right or []})
    return list(merged.values())


class AnalysisState(TypedDict, total=False):
    # Inputs
    analysis_id: str
    created_at: str
    cv_meta: dict  # kind, filename, size, lines, multi_column: never the bytes
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
    review_banners: list[dict]
    parse_warnings: list[dict]
    assessment_drafts: Annotated[dict, merge_by_id]
    assessments: dict
    barrier_items: list[dict]  # the model's barriers, then the merged list once recomputed
    recency: dict  # requirement ID -> RecencyCheck
    hidden_risks: list[dict]
    screening_flags: list[dict]
    score: dict
    verdict: dict

    # Optimize and build
    suggestions: Annotated[list[dict], merge_items_by_id]
    refusals: list[dict]  # not viable: requirements and refused suggestions
    decisions: dict | None
    document: dict | None
    built_by: str | None
    build_report: dict | None

    # Bookkeeping
    errors: Annotated[list, operator.add]
    usage: Annotated[list, operator.add]


class MatchTask(TypedDict):
    """Compact payload for one parallel matching call."""

    requirement_ids: list[str]
    requirements_block: str
    cv_block: str
