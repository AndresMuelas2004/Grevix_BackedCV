"""Create an analysis (streamed with server-sent events) and read it back."""

import json
import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import ValidationError

from backedcv.api.errors import ApiError
from backedcv.api.projection import project
from backedcv.domain.models import CandidateFacts
from backedcv.graph.builder import run_config
from backedcv.ingestion import read_cv, read_cv_text
from backedcv.ingestion.reader import MAX_BYTES, ReadResult

router = APIRouter(tags=["analyses"])

JOB_MIN_CHARS = 150
JOB_MAX_CHARS = 20_000


@dataclass
class NewAnalysis:
    cv: ReadResult
    job_text: str
    facts: CandidateFacts


async def analysis_input(
    job_text: Annotated[str, Form()],
    cv_text: Annotated[str | None, Form()] = None,
    cv_file: Annotated[UploadFile | None, File()] = None,
    facts: Annotated[str | None, Form()] = None,
) -> NewAnalysis:
    """Runs before the stream opens, so bad input gets a proper 4xx JSON error."""
    job_text = job_text.strip()
    if len(job_text) < JOB_MIN_CHARS:
        raise ApiError(422, "job_too_short", "Paste the full job posting.")
    if len(job_text) > JOB_MAX_CHARS:
        raise ApiError(
            422, "job_too_long", f"Job postings are limited to {JOB_MAX_CHARS:,} characters."
        )

    if cv_file is not None and cv_file.filename:
        data = await cv_file.read(MAX_BYTES + 1)
        cv = read_cv(data, cv_file.filename)
    elif cv_text and cv_text.strip():
        cv = read_cv_text(cv_text)
    else:
        raise ApiError(422, "cv_missing", "Upload a CV file or paste its text.")

    try:
        parsed_facts = CandidateFacts.model_validate(json.loads(facts)) if facts else None
    except (ValueError, ValidationError) as exc:
        raise ApiError(422, "facts_invalid", "The answers could not be read.") from exc
    return NewAnalysis(cv, job_text, parsed_facts or CandidateFacts())


@router.post("/analyses", response_class=EventSourceResponse)
async def create_analysis(
    request: Request, new: Annotated[NewAnalysis, Depends(analysis_input)]
) -> AsyncIterable[ServerSentEvent]:
    graph, locks = request.app.state.graph, request.app.state.locks
    analysis_id = str(uuid.uuid4())
    config = run_config(analysis_id)
    locks.acquire(analysis_id)
    initial = {
        "analysis_id": analysis_id,
        "created_at": datetime.now(UTC).isoformat(),
        "cv_meta": {
            "kind": new.cv.kind,
            "filename": new.cv.filename,
            "size": new.cv.size,
            "lines": len(new.cv.lines),
            "multi_column": new.cv.multi_column,
        },
        "cv_lines": [line.model_dump() for line in new.cv.lines],
        "job_text": new.job_text,
        "facts": new.facts.model_dump(),
        "excluded_ids": [],
        "included_flagged_ids": [],
    }

    yield ServerSentEvent(event="created", data={"analysis_id": analysis_id})
    async with locks.held(analysis_id):
        try:
            async for mode, chunk in graph.astream(
                initial, config, stream_mode=["custom", "updates"]
            ):
                if mode == "custom":
                    yield ServerSentEvent(event="progress", data=chunk)
        except Exception as exc:
            yield ServerSentEvent(
                event="error",
                data={
                    "code": "analysis_failed",
                    "title": "The analysis could not finish.",
                    "detail": type(exc).__name__,
                },
            )
            return
    snapshot = await graph.aget_state(config)
    yield ServerSentEvent(event="report", data=project(analysis_id, snapshot))


@router.get("/analyses/{analysis_id}")
async def get_analysis(request: Request, analysis_id: str) -> dict:
    graph, locks = request.app.state.graph, request.app.state.locks
    snapshot = await graph.aget_state(run_config(analysis_id))
    if not snapshot.values:
        raise ApiError(404, "not_found", "This analysis does not exist or has expired.")
    return project(analysis_id, snapshot, running=locks.is_running(analysis_id))
