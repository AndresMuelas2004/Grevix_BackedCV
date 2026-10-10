"""What the frontend sees of an analysis: a projection of the graph state, never file bytes."""

from typing import Any


def status_of(snapshot: Any, running: bool) -> str:
    if running:
        return "running"
    if not snapshot.next:
        return "done"
    if getattr(snapshot, "interrupts", None):
        return "paused"
    return "stalled"


def usage_total(usage: list[dict]) -> dict:
    return {
        "calls": len(usage),
        "input_tokens": sum(u.get("input_tokens", 0) for u in usage),
        "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
        "cost_usd": round(sum(u.get("cost_usd", 0.0) for u in usage), 4),
        "models": sorted({u.get("model", "") for u in usage}),
    }


def project(analysis_id: str, snapshot: Any, running: bool = False) -> dict:
    values = snapshot.values or {}
    return {
        "analysis_id": analysis_id,
        "status": status_of(snapshot, running),
        "stage": _stage(snapshot),
        "cv_meta": values.get("cv_meta"),
        "cv": values.get("cv"),
        "job": values.get("job"),
        "job_notes": values.get("job_notes", []),
        "flags": values.get("flags", []),
        "banners": values.get("banners", []),
        "assessments": values.get("assessments", {}),
        "score": values.get("score"),
        "verdict": values.get("verdict"),
        "facts": values.get("facts") or {},
        "excluded_ids": values.get("excluded_ids") or [],
        "included_flagged_ids": values.get("included_flagged_ids") or [],
        "errors": values.get("errors", []),
        "usage": usage_total(values.get("usage", [])),
    }


def _stage(snapshot: Any) -> str | None:
    for item in getattr(snapshot, "interrupts", None) or ():
        value = getattr(item, "value", None)
        if isinstance(value, dict) and "stage" in value:
            return value["stage"]
    return None
