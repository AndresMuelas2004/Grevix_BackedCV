"""Create an analysis (streamed with server-sent events) and read it back. The run starts before the
stream opens and keeps going if the client leaves: the stream only listens to it (api/runs.py)."""

import json
import uuid
from collections.abc import AsyncIterable
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import ValidationError

from backedcv.api.errors import ApiError
from backedcv.api.projection import project
from backedcv.api.rate_limit import count_model_run
from backedcv.api.runs import Run, stream_graph
from backedcv.domain.models import CandidateFacts
from backedcv.domain.text import normalize_text
from backedcv.graph.builder import run_config
from backedcv.ingestion import read_cv, read_cv_text
from backedcv.ingestion.reader import MAX_BYTES, ReadResult

router = APIRouter(tags=["analyses"])

JOB_MIN_CHARS = 150
JOB_MAX_CHARS = 20_000
ANALYSIS_FAILED = ("analysis_failed", "The analysis could not finish.")


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
    """Runs before the stream opens, so bad input gets a proper 4xx JSON error. The posting takes
    its canonical form here, before anything reads it (the CV does in `ingestion`)."""
    job_text = normalize_text(job_text)
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


async def start_analysis(
    request: Request, new: Annotated[NewAnalysis, Depends(analysis_input)]
) -> Run:
    """Counts the run and starts it before the stream opens, so a refusal is a JSON error."""
    count_model_run(request)
    graph, ledger = request.app.state.graph, request.app.state.ledger
    analysis_id = str(uuid.uuid4())
    config = run_config(analysis_id)
    created = datetime.now(UTC)
    initial = {
        "analysis_id": analysis_id,
        "created_at": created.isoformat(),
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

    async def work(run: Run) -> dict:
        run.emit(ServerSentEvent(event="created", data={"analysis_id": analysis_id}))
        ledger.add(analysis_id, created)
        await stream_graph(graph, initial, config, run)
        return project(analysis_id, await graph.aget_state(config))

    request.app.state.locks.acquire(analysis_id)
    return request.app.state.runs.launch(analysis_id, work, done="report", failed=ANALYSIS_FAILED)


@router.post("/analyses", response_class=EventSourceResponse)
async def create_analysis(
    run: Annotated[Run, Depends(start_analysis)],
) -> AsyncIterable[ServerSentEvent]:
    """Streams `created`, the `progress` steps, then `report` (or `error`)."""
    async with aclosing(run.listen()) as events:
        async for event in events:
            yield event


@router.get("/analyses/{analysis_id}")
async def get_analysis(request: Request, analysis_id: str) -> dict:
    graph, runs = request.app.state.graph, request.app.state.runs
    running = runs.is_running(analysis_id)
    snapshot = await graph.aget_state(run_config(analysis_id))
    # A run can start or end during the read, so the flag is checked on both sides of it.
    running = running or runs.is_running(analysis_id)
    if not snapshot.values and not running:
        raise ApiError(404, "not_found", "This analysis does not exist or has expired.")
    return project(analysis_id, snapshot, running=running, error=runs.failure(analysis_id))
