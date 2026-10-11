"""The optimize, build and verify steps. Streams resume the paused run; every refusal (429, 404,
409, 422) is decided before the stream opens, so it arrives as a JSON error."""

from collections.abc import AsyncIterable, Callable
from contextlib import aclosing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langgraph.types import Command
from pydantic import BaseModel, StringConstraints

from backedcv.api.errors import ApiError, stream_error
from backedcv.api.projection import project, waiting_at_report, waiting_at_review
from backedcv.api.rate_limit import limit_model_run
from backedcv.domain.guards import apply_guards
from backedcv.domain.models import JobPosting, ParsedCV, ReviewDecisions, Suggestion, Verification
from backedcv.graph.builder import run_config
from backedcv.graph.optimize_nodes import make_optimize_nodes
from backedcv.llm.structured import StructuredLLM

router = APIRouter(tags=["analyses"])

OPTIMIZE_FAILED = ("optimize_failed", "The suggestions could not be made.")
BUILD_FAILED = ("build_failed", "The CV could not be built.")


class SuggestionEdit(BaseModel):
    after: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


async def claim_optimize(request: Request, analysis_id: str) -> None:
    await _claim(request, analysis_id, _require_report)


async def claim_build(
    request: Request, analysis_id: str, decisions: ReviewDecisions
) -> ReviewDecisions:
    """The decisions are checked before the stream opens, and they are the resume value."""

    def refuse(snapshot: Any) -> None:
        _require_review(snapshot, "The CV can only be built while the suggestions wait for review.")
        _check_decisions(decisions, snapshot.values)

    await _claim(request, analysis_id, refuse)
    return decisions


@router.post(
    "/analyses/{analysis_id}/optimize",
    response_class=EventSourceResponse,
    dependencies=[Depends(limit_model_run), Depends(claim_optimize)],
)
async def optimize(request: Request, analysis_id: str) -> AsyncIterable[ServerSentEvent]:
    """Writes the suggestions, verifies each one, and pauses for the user's review."""
    # Never {}: LangGraph ignores an empty resume and the run would not move on.
    stream = _run_stream(
        request, analysis_id, {"action": "optimize"}, done="suggestions", failed=OPTIMIZE_FAILED
    )
    async with aclosing(stream):
        async for event in stream:
            yield event


@router.post(
    "/analyses/{analysis_id}/build",
    response_class=EventSourceResponse,
    dependencies=[Depends(limit_model_run)],
)
async def build(
    request: Request,
    analysis_id: str,
    decisions: Annotated[ReviewDecisions, Depends(claim_build)],
) -> AsyncIterable[ServerSentEvent]:
    """Applies the accepted suggestions, orders the CV and runs the final checks."""
    stream = _run_stream(
        request, analysis_id, decisions.model_dump(), done="built", failed=BUILD_FAILED
    )
    async with aclosing(stream):
        async for event in stream:
            yield event


@router.post(
    "/analyses/{analysis_id}/suggestions/{suggestion_id}/verify",
    dependencies=[Depends(limit_model_run)],
)
async def verify_suggestion(
    request: Request, analysis_id: str, suggestion_id: str, edit: SuggestionEdit
) -> dict:
    """Checks an edited suggestion again: the guards first, then the verifier if they pass."""
    graph, locks = request.app.state.graph, request.app.state.locks
    config = run_config(analysis_id)
    locks.acquire(analysis_id)
    async with locks.held(analysis_id):
        snapshot = await graph.aget_state(config)
        if not snapshot.values:
            raise ApiError(404, "not_found", "This analysis does not exist or has expired.")
        _require_review(snapshot, "Suggestions can only be edited while they wait for review.")
        update = await _check_edit(
            request.app.state.llm, snapshot.values, suggestion_id, edit.after
        )
        # Written as if the verifier had just run, so the run still waits at the review.
        await graph.aupdate_state(config, update, as_node="verify_batch")
    return project(analysis_id, await graph.aget_state(config))


async def _claim(request: Request, analysis_id: str, refuse: Callable[[Any], None]) -> None:
    """Takes the run lock (409 while a run holds it), then lets `refuse` check the analysis.

    A refused request gives the lock back. An accepted one keeps it until its stream ends.
    """
    locks = request.app.state.locks
    locks.acquire(analysis_id)
    try:
        snapshot = await request.app.state.graph.aget_state(run_config(analysis_id))
        if not snapshot.values:
            raise ApiError(404, "not_found", "This analysis does not exist or has expired.")
        refuse(snapshot)
    except BaseException:
        locks.release(analysis_id)
        raise


def _require_report(snapshot: Any) -> None:
    if not waiting_at_report(snapshot):
        raise ApiError(409, "wrong_stage", "Suggestions can only be made once the report is ready.")


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


async def _check_edit(llm: StructuredLLM, values: dict, suggestion_id: str, after: str) -> dict:
    """The state update for one edited suggestion: guards first, then a new verification."""
    row = next((r for r in values.get("suggestions") or [] if r["id"] == suggestion_id), None)
    if row is None:
        raise ApiError(404, "suggestion_not_found", "This suggestion does not exist.")
    cv = ParsedCV.model_validate(values["cv"])
    job = JobPosting.model_validate(values["job"])
    edited = Suggestion.model_validate(row).model_copy(
        update={"after": after, "edited_by_user": True, "verification": Verification()}
    )
    checked = apply_guards(edited, cv, job)
    if checked.verification.status != "pending":  # a hard guard failed: the model is not asked
        return {"suggestions": [checked.model_dump()]}
    verify_batch = make_optimize_nodes(llm)["verify_batch"]
    return await verify_batch({"cv": values["cv"], "group": [checked.model_dump()]})


async def _run_stream(
    request: Request,
    analysis_id: str,
    resume: Any,
    done: str,
    failed: tuple[str, str],
) -> AsyncIterable[ServerSentEvent]:
    """Resumes the paused run and streams its progress. It ends with the `done` event, or with an
    `error` event (code and title from `failed`) when the run fails."""
    graph, locks = request.app.state.graph, request.app.state.locks
    config = run_config(analysis_id)
    async with locks.held(analysis_id):
        try:
            async for mode, chunk in graph.astream(
                Command(resume=resume), config, stream_mode=["custom", "updates"]
            ):
                if mode == "custom":
                    yield ServerSentEvent(event="progress", data=chunk)
        except Exception as exc:
            code, title = failed
            yield stream_error(code, title, exc)
            return
    yield ServerSentEvent(event=done, data=project(analysis_id, await graph.aget_state(config)))
