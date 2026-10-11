"""Inputs given after the report (answers, toggles): the score is recomputed, no model call."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backedcv.api.errors import ApiError
from backedcv.api.projection import project, waiting_at_report
from backedcv.domain.models import CandidateFacts, JobPosting
from backedcv.graph.builder import run_config
from backedcv.graph.recompute import recompute

router = APIRouter(tags=["analyses"])


class InputsUpdate(BaseModel):
    """Omitted fields keep their current value; a list that is sent replaces the old list."""

    facts: CandidateFacts | None = None  # answers: a fact left out keeps its old answer
    excluded_ids: list[str] | None = None  # requirements the user marks as not relevant
    included_flagged_ids: list[str] | None = None  # flagged requirements to count again


@router.patch("/analyses/{analysis_id}/inputs")
async def update_inputs(request: Request, analysis_id: str, update: InputsUpdate) -> dict:
    graph, locks = request.app.state.graph, request.app.state.locks
    config = run_config(analysis_id)
    locks.acquire(analysis_id)
    async with locks.held(analysis_id):
        snapshot = await graph.aget_state(config)
        if not snapshot.values:
            raise ApiError(404, "not_found", "This analysis does not exist or has expired.")
        if not waiting_at_report(snapshot):
            raise ApiError(409, "not_paused", "Inputs can only change once the report is ready.")
        changes = _merge(snapshot.values, update)
        values = {**changes, **recompute({**snapshot.values, **changes})}
        # Written as if the score node had just run; the next node is still the optimize pause.
        await graph.aupdate_state(config, values, as_node="score_and_verdict")
    return project(analysis_id, await graph.aget_state(config))


def _merge(state: dict, update: InputsUpdate) -> dict:
    """The input values after the update. Unknown requirement IDs are refused before any write."""
    known = {req.id for req in JobPosting.model_validate(state["job"]).requirements}
    sent = [*(update.excluded_ids or []), *(update.included_flagged_ids or [])]
    unknown = sorted(set(sent) - known)
    if unknown:
        raise ApiError(
            422, "inputs_invalid", "Some requirements are not in this posting.", ", ".join(unknown)
        )
    return {
        "facts": _merge_facts(state.get("facts"), update.facts).model_dump(),
        "excluded_ids": _sent_or_current(update.excluded_ids, state.get("excluded_ids")),
        "included_flagged_ids": _sent_or_current(
            update.included_flagged_ids, state.get("included_flagged_ids")
        ),
    }


def _merge_facts(current: dict | None, sent: CandidateFacts | None) -> CandidateFacts:
    """Answers that are sent are added to the ones already given, so one answer keeps the rest.
    Any other field that is sent replaces its old value."""
    old = CandidateFacts.model_validate(current or {})
    if sent is None:
        return old
    changes = sent.model_dump(exclude_unset=True)
    answers = {**old.answers, **changes.pop("answers", {})}
    return CandidateFacts.model_validate({**old.model_dump(), **changes, "answers": answers})


def _sent_or_current(sent: list[str] | None, current: list[str] | None) -> list[str]:
    return list(current or []) if sent is None else sent
