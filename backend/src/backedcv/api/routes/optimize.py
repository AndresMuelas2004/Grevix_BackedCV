"""The optimize, build and verify steps. Every refusal (429, 404, 409, 422) is decided before the
stream opens, so it arrives as a JSON error."""

import asyncio
from collections.abc import AsyncIterable, Callable
from contextlib import aclosing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langgraph.types import Command
from pydantic import BaseModel, StringConstraints

from backedcv.api.errors import ApiError
from backedcv.api.projection import (
    BUILD_STEP,
    OPTIMIZE_STEP,
    project,
    shown_errors,
    stalled_in,
    waiting_at_report,
    waiting_at_review,
)
from backedcv.api.rate_limit import count_model_run
from backedcv.api.runs import Run, emit_progress, stream_graph
from backedcv.domain.corroboration import (
    apply_pass,
    backed_pass,
    barrier_pass,
    recency_pass,
    refusals_from,
)
from backedcv.domain.guards import apply_guards
from backedcv.domain.models import JobPosting, ParsedCV, ReviewDecisions, Suggestion, Verification
from backedcv.domain.recency import line_last_used
from backedcv.graph.builder import run_config
from backedcv.graph.optimize_nodes import make_optimize_nodes
from backedcv.graph.recompute import recency_of, risks_of, today_of
from backedcv.graph.state import merge_items_by_id
from backedcv.llm.structured import StructuredLLM

router = APIRouter(tags=["analyses"])

OPTIMIZE_FAILED = ("optimize_failed", "The suggestions could not be made.")
BUILD_FAILED = ("build_failed", "The CV could not be built.")


class SuggestionEdit(BaseModel):
    after: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


async def _claim(request: Request, analysis_id: str, refuse: Callable[[Any], None]) -> Any:
    """Takes the run lock (409 while a run holds it), lets `refuse` check the analysis, and counts
    the run. A refused request gives the lock back; an accepted one keeps it until its run ends."""
    locks = request.app.state.locks
    locks.acquire(analysis_id)
    try:
        snapshot = await request.app.state.graph.aget_state(run_config(analysis_id))
        if not snapshot.values:
            raise ApiError(404, "not_found", "This analysis does not exist or has expired.")
        refuse(snapshot)
        count_model_run(request)
    except BaseException:
        locks.release(analysis_id)
        raise
    return snapshot


async def start_optimize(request: Request, analysis_id: str) -> Run:
    """Starts the optimize run. A failed optimize runs again from the step that failed. A suggest
    step that failed inside the graph (the review has no suggestions) runs again from the review."""
    snapshot = await _claim(request, analysis_id, _require_report)
    graph, config = request.app.state.graph, run_config(analysis_id)
    llm, values = request.app.state.llm, snapshot.values
    suggest_again = _suggest_failed(snapshot)
    # Never {}: LangGraph ignores an empty resume and the run would not move on.
    resume = Command(resume={"action": "optimize"}) if waiting_at_report(snapshot) else None

    async def work(run: Run) -> dict:
        if suggest_again:
            await _suggest_again(run, llm, graph, config, values)
        else:
            await stream_graph(graph, resume, config, run)
        return project(analysis_id, await graph.aget_state(config))

    return request.app.state.runs.launch(
        analysis_id, work, done="suggestions", failed=OPTIMIZE_FAILED
    )


async def start_build(request: Request, analysis_id: str, decisions: ReviewDecisions) -> Run:
    """Starts the build run. A failed build is run again with the decisions it is sent."""

    def refuse(snapshot: Any) -> None:
        if not (waiting_at_review(snapshot) or stalled_in(snapshot, BUILD_STEP)):
            raise ApiError(
                409,
                "wrong_stage",
                "The CV can only be built while the suggestions wait for review, "
                "or after a failed build.",
            )
        _check_decisions(decisions, snapshot.values)

    snapshot = await _claim(request, analysis_id, refuse)
    graph, config = request.app.state.graph, run_config(analysis_id)
    decided = decisions.model_dump()
    waiting = waiting_at_review(snapshot)

    async def work(run: Run) -> dict:
        if waiting:
            resume = Command(resume=decided)
        else:
            # The failed build starts again from its first step, with these decisions.
            await graph.aupdate_state(config, {"decisions": decided}, as_node="await_review")
            resume = None
        await stream_graph(graph, resume, config, run)
        return project(analysis_id, await graph.aget_state(config))

    return request.app.state.runs.launch(analysis_id, work, done="built", failed=BUILD_FAILED)


@router.post(
    "/analyses/{analysis_id}/optimize",
    response_class=EventSourceResponse,
)
async def optimize(run: Annotated[Run, Depends(start_optimize)]) -> AsyncIterable[ServerSentEvent]:
    """Writes the suggestions, verifies each one, and pauses for the user's review."""
    async with aclosing(run.listen()) as events:
        async for event in events:
            yield event


@router.post(
    "/analyses/{analysis_id}/build",
    response_class=EventSourceResponse,
)
async def build(run: Annotated[Run, Depends(start_build)]) -> AsyncIterable[ServerSentEvent]:
    """Applies the accepted suggestions, orders the CV and runs the final checks."""
    async with aclosing(run.listen()) as events:
        async for event in events:
            yield event


@router.post("/analyses/{analysis_id}/suggestions/{suggestion_id}/verify")
async def verify_suggestion(
    request: Request, analysis_id: str, suggestion_id: str, edit: SuggestionEdit
) -> dict:
    """Checks an edited suggestion again: the guards, then the verifier if they pass, then the
    corroboration gate."""
    graph, locks = request.app.state.graph, request.app.state.locks
    config = run_config(analysis_id)
    locks.acquire(analysis_id)
    async with locks.held(analysis_id):
        snapshot = await graph.aget_state(config)
        if not snapshot.values:
            raise ApiError(404, "not_found", "This analysis does not exist or has expired.")
        _require_review(snapshot, "Suggestions can only be edited while they wait for review.")
        row = _find_suggestion(snapshot.values, suggestion_id)
        count_model_run(request)
        update = await _check_edit(request.app.state.llm, snapshot.values, row, edit.after)
        # Written as if the gate had just run, so the run still waits at the review.
        await graph.aupdate_state(config, update, as_node="gate_barriers")
    return project(analysis_id, await graph.aget_state(config))


def _require_report(snapshot: Any) -> None:
    if not (
        waiting_at_report(snapshot)
        or stalled_in(snapshot, OPTIMIZE_STEP)
        or _suggest_failed(snapshot)
    ):
        raise ApiError(409, "wrong_stage", "Suggestions can only be made once the report is ready.")


def _suggest_failed(snapshot: Any) -> bool:
    """The suggest step failed inside the graph: the run still reached the review, with no
    suggestions and an error from that step, because the graph does not stop on it."""
    values = snapshot.values or {}
    return (
        waiting_at_review(snapshot)
        and not values.get("suggestions")
        and any(error.get("node") == "suggest" for error in shown_errors(values.get("errors")))
    )


def _require_review(snapshot: Any, message: str) -> None:
    if not waiting_at_review(snapshot):
        raise ApiError(409, "wrong_stage", message)


def _check_decisions(decisions: ReviewDecisions, values: dict) -> None:
    """Every decided ID must be a suggestion of this analysis, and only verified ones may be
    accepted. A suggestion cannot be both accepted and rejected."""
    rows = {row["id"]: Suggestion.model_validate(row) for row in values.get("suggestions") or []}
    unknown = sorted({*decisions.accepted, *decisions.rejected} - set(rows))
    if unknown:
        raise _invalid("Some suggestions are not part of this analysis.", unknown)
    both = sorted(set(decisions.accepted) & set(decisions.rejected))
    if both:
        raise _invalid("A suggestion cannot be both accepted and rejected.", both)
    unverified = sorted(
        sid for sid in decisions.accepted if rows[sid].verification.status != "verified"
    )
    if unverified:
        raise _invalid("Only verified suggestions can be accepted.", unverified)


def _invalid(title: str, ids: list[str]) -> ApiError:
    return ApiError(422, "decisions_invalid", title, ", ".join(ids))


def _find_suggestion(values: dict, suggestion_id: str) -> dict:
    row = next((r for r in values.get("suggestions") or [] if r["id"] == suggestion_id), None)
    if row is None:
        raise ApiError(404, "suggestion_not_found", "This suggestion does not exist.")
    return row


async def _suggest_again(
    run: Run, llm: StructuredLLM, graph: Any, config: dict, values: dict
) -> None:
    """Runs the suggest step here, because the graph cannot run a step again from the review, then
    the verification groups and the gate as the graph would. Written as if gate_barriers had just
    run, so the run still waits at the review; `resolves` supersedes the failed step's error."""
    nodes = make_optimize_nodes(llm)
    emit_progress(run, "suggest", "started")
    found = await nodes["suggest"](values)
    suggestions: list[dict] = found["suggestions"]
    emit_progress(run, "suggest", "done", suggestions=len(suggestions))
    usage, errors = list(found.get("usage", [])), list(found.get("errors", []))

    routed = nodes["route_verification"]({**values, "suggestions": suggestions})
    if isinstance(routed, list):  # one verification per CV section, grouped as the graph does
        for _ in routed:
            emit_progress(run, "verify", "started")
        results = await asyncio.gather(*(nodes["verify_batch"](send.arg) for send in routed))
        checked = {row["id"]: row for row in suggestions}
        for result in results:
            emit_progress(run, "verify", "done", suggestions=len(result["suggestions"]))
            checked.update({row["id"]: row for row in result["suggestions"]})
            usage += result.get("usage", [])
            errors += result.get("errors", [])
        suggestions = list(checked.values())

    update = {
        "suggestions": suggestions,
        "usage": usage,
        "errors": [{"resolves": "suggest"}, *errors],
    }
    gated = _corroborate(values, update)
    await graph.aupdate_state(config, gated, as_node="gate_barriers")


async def _check_edit(llm: StructuredLLM, values: dict, row: dict, after: str) -> dict:
    """The state update for one edited suggestion: guards, verification, corroboration gate."""
    cv = ParsedCV.model_validate(values["cv"])
    job = JobPosting.model_validate(values["job"])
    edited = Suggestion.model_validate(row).model_copy(
        update={"after": after, "edited_by_user": True, "verification": Verification()}
    )
    checked = apply_guards(edited, cv, job)
    if checked.verification.status == "pending":
        verify_batch = make_optimize_nodes(llm)["verify_batch"]
        update = await verify_batch({"cv": values["cv"], "group": [checked.model_dump()]})
    else:  # a hard guard failed: the model is not asked
        update = {"suggestions": [checked.model_dump()]}
    return _corroborate(values, update)


def _corroborate(values: dict, update: dict) -> dict:
    """Runs the corroboration gate (backed, recency and barrier passes) on the suggestions of an
    update, as the graph does after the verifier. Only the update's suggestions get passes, so
    none is checked twice. Suggestion refusals are rebuilt; requirement refusals do not depend on
    a suggestion and are kept."""
    cv = ParsedCV.model_validate(values["cv"])
    today = today_of(values)
    last_used = line_last_used(cv, today)
    recency, risks = recency_of(values), risks_of(values)
    gated = []
    for row in update["suggestions"]:
        s = Suggestion.model_validate(row)
        s = apply_pass(s, backed_pass(s))
        s = apply_pass(s, recency_pass(s, recency, last_used, today))
        gated.append(apply_pass(s, barrier_pass(s, risks)))
    rows = [s.model_dump() for s in gated]
    everything = [
        Suggestion.model_validate(r) for r in merge_items_by_id(values.get("suggestions"), rows)
    ]
    refused = refusals_from(everything)
    kept = [r for r in values.get("refusals") or [] if r.get("suggestion_id") is None]
    refusals = [*kept, *(r.model_dump() for r in refused)]
    return {**update, "suggestions": rows, "refusals": refusals}
