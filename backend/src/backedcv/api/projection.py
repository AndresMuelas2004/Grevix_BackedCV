"""What the frontend sees of an analysis: a projection of the graph state, never file bytes."""

from typing import Any

REPORT_NODE = "await_optimize"  # the node that pauses once the report is ready
REPORT_STAGE = "report_ready"
REVIEW_NODE = "await_review"  # the node that pauses for the user's decisions on suggestions
REVIEW_STAGE = "review_ready"
BUILT_STAGE = "built"  # the run reached its end
_PAUSE_STAGES = {REPORT_NODE: REPORT_STAGE, REVIEW_NODE: REVIEW_STAGE}
# The nodes an optimize can stop in: the suggestions, their verification, then the two gates.
OPTIMIZE_STEP = frozenset({"suggest", "verify_batch", "gate_recency", "gate_barriers"})
BUILD_STEP = frozenset({"build_cv", "final_checks"})  # the nodes a build can stop in


def status_of(snapshot: Any, running: bool, failed: bool = False) -> str:
    if running:
        return "running"
    if failed:  # the last run failed: its error is in the projection
        return "stalled"
    if not snapshot.next:
        return "done"
    if getattr(snapshot, "interrupts", None) or _stage(snapshot):
        return "paused"
    return "stalled"


def waiting_at_report(snapshot: Any) -> bool:
    return _stage(snapshot) == REPORT_STAGE


def waiting_at_review(snapshot: Any) -> bool:
    return _stage(snapshot) == REVIEW_STAGE


def stalled_in(snapshot: Any, step: frozenset[str]) -> bool:
    """True when a run stopped inside `step` (it failed there), so the step can run again."""
    pending = set(snapshot.next or ())
    return bool(pending) and pending <= step


def usage_total(usage: list[dict]) -> dict:
    return {
        "calls": len(usage),
        "cached_calls": sum(1 for u in usage if u.get("cached")),
        "input_tokens": sum(u.get("input_tokens", 0) for u in usage),
        "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
        "cost_usd": round(sum(u.get("cost_usd", 0.0) for u in usage), 4),
        "models": sorted({u.get("model", "") for u in usage}),
    }


def shown_errors(errors: list[dict] | None) -> list[dict]:
    """The error log as the frontend sees it. The graph only appends to the log, so a step that ran
    again writes a `resolves` entry: the errors of that step written before it are not shown."""
    shown: list[dict] = []
    for entry in errors or []:
        if "resolves" in entry:
            shown = [error for error in shown if error.get("node") != entry["resolves"]]
        else:
            shown.append(entry)
    return shown


def project(
    analysis_id: str, snapshot: Any, running: bool = False, error: dict | None = None
) -> dict:
    values = snapshot.values or {}
    projection = {
        "analysis_id": analysis_id,
        "status": status_of(snapshot, running, failed=error is not None),
        "stage": _stage(snapshot),
        "cv_meta": values.get("cv_meta"),
        "cv": values.get("cv"),
        "job": values.get("job"),
        "job_notes": values.get("job_notes", []),
        "flags": values.get("flags", []),
        "banners": [*(values.get("banners") or []), *(values.get("review_banners") or [])],
        "parse_warnings": values.get("parse_warnings") or [],
        "assessments": values.get("assessments", {}),
        "score": values.get("score"),
        "verdict": values.get("verdict"),
        "hidden_risks": values.get("hidden_risks") or [],
        "screening_flags": values.get("screening_flags") or [],
        "recency": values.get("recency") or {},
        "refusals": values.get("refusals") or [],
        "suggestions": values.get("suggestions") or [],
        "decisions": values.get("decisions"),
        "document": values.get("document"),
        "build_report": values.get("build_report"),
        "facts": values.get("facts") or {},
        "excluded_ids": values.get("excluded_ids") or [],
        "included_flagged_ids": values.get("included_flagged_ids") or [],
        "errors": shown_errors(values.get("errors")),
        "usage": usage_total(values.get("usage", [])),
    }
    if error is not None:  # the same body as the `error` event of the run that failed
        projection["error"] = error
    return projection


def _stage(snapshot: Any) -> str | None:
    for item in getattr(snapshot, "interrupts", None) or ():
        value = getattr(item, "value", None)
        if isinstance(value, dict) and "stage" in value:
            return value["stage"]
    # After an input update the pause is the next node, and its interrupt is not recorded yet.
    for node in snapshot.next or ():
        if node in _PAUSE_STAGES:
            return _PAUSE_STAGES[node]
    if snapshot.values and not snapshot.next:
        return BUILT_STAGE
    return None
