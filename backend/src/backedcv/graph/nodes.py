"""Graph nodes. Each LLM node degrades gracefully where the feature is optional."""

import contextlib
import logging
from datetime import date

from langgraph.config import get_stream_writer
from langgraph.types import Send, interrupt

from backedcv.domain.builders import build_job, build_parsed_cv
from backedcv.domain.keywords import keyword_hits
from backedcv.domain.models import CVLine, JobPosting, ParsedCV
from backedcv.domain.rules.absurd import flag_requirements
from backedcv.graph.recompute import recompute
from backedcv.graph.state import AnalysisState, MatchTask
from backedcv.llm.drafts import CVStructureDraft, JobExtractionDraft, MatchChunkDraft
from backedcv.llm.prompt_loader import load_prompt
from backedcv.llm.structured import StructuredLLM

log = logging.getLogger(__name__)
CHUNK_SIZE = 8


def _progress(step: str, status: str, **extra) -> None:
    # Outside a streaming run (direct calls in tests) there is no writer.
    with contextlib.suppress(RuntimeError):
        get_stream_writer()({"type": "progress", "step": step, "status": status, **extra})


def _error(node: str, exc: Exception) -> dict:
    log.warning("node %s failed: %s", node, exc)
    return {"node": node, "error": type(exc).__name__, "detail": str(exc)[:300]}


def make_nodes(llm: StructuredLLM):
    async def prepare_cv(state: AnalysisState) -> dict:
        _progress("prepare_cv", "started")
        lines = [CVLine.model_validate(row) for row in state["cv_lines"]]
        numbered = "\n".join(f"{line.id} | {line.text}" for line in lines)
        update: dict = {}
        try:
            draft, usage = await llm.run(
                load_prompt("structure_cv"),
                f"<cv_lines>\n{numbered}\n</cv_lines>",
                CVStructureDraft,
                node="prepare_cv",
            )
            update["usage"] = [usage]
        except Exception as exc:  # structure is optional: matching works on lines alone
            draft = None
            update["errors"] = [_error("prepare_cv", exc)]
        cv = build_parsed_cv(lines, draft, today=date.today())
        _progress("prepare_cv", "done")
        return {**update, "cv": cv.model_dump()}

    async def prepare_job(state: AnalysisState) -> dict:
        _progress("prepare_job", "started")
        posting = state["job_text"]
        draft, usage = await llm.run(
            load_prompt("extract_job"),
            f"<job_posting>\n{posting}\n</job_posting>",
            JobExtractionDraft,
            node="prepare_job",
        )
        job, notes = build_job(posting, draft)
        flags = flag_requirements(job)
        _progress("prepare_job", "done", requirements=len(job.requirements))
        return {
            "job": job.model_dump(),
            "job_notes": notes,
            "flags": [f.model_dump() for f in flags],
            "banners": [],
            "usage": [usage],
        }

    async def plan_matching(state: AnalysisState) -> dict:
        _progress("match", "started")
        return {}

    def route_matching(state: AnalysisState):
        job = JobPosting.model_validate(state["job"])
        if not job.requirements:
            return "score_and_verdict"  # an empty Send list would end the graph early
        cv = ParsedCV.model_validate(state["cv"])
        cv_block = cv.numbered()
        tasks = []
        for start in range(0, len(job.requirements), CHUNK_SIZE):
            chunk = job.requirements[start : start + CHUNK_SIZE]
            rows = []
            for req in chunk:
                hits = keyword_hits(req, cv.lines)
                hint = ", ".join(sorted({h.line_id for h in hits})) or "none"
                rows.append(
                    f"{req.id} | {req.label} | {req.importance} | {req.category}"
                    f" | quote: {req.quote} | exact_hits: {hint}"
                )
            tasks.append(
                Send(
                    "match_chunk",
                    MatchTask(
                        requirement_ids=[r.id for r in chunk],
                        requirements_block="\n".join(rows),
                        cv_block=cv_block,
                    ),
                )
            )
        return tasks

    async def match_chunk(task: MatchTask) -> dict:
        try:
            draft, usage = await llm.run(
                load_prompt("match_requirements"),
                f"<requirements>\n{task['requirements_block']}\n</requirements>\n\n"
                f"<cv_lines>\n{task['cv_block']}\n</cv_lines>",
                MatchChunkDraft,
                node="match_chunk",
            )
        except Exception as exc:  # those requirements fall back to literal matching
            return {"errors": [_error("match_chunk", exc)]}
        wanted = set(task["requirement_ids"])
        drafts = {
            a.requirement_id: a.model_dump()
            for a in draft.assessments
            if a.requirement_id in wanted
        }
        _progress("match", "chunk_done", requirements=len(drafts))
        return {"assessment_drafts": drafts, "usage": [usage]}

    async def score_and_verdict(state: AnalysisState) -> dict:
        _progress("score", "started")
        update = recompute(state)
        _progress("score", "done")
        return update

    async def await_optimize(state: AnalysisState) -> dict:
        # Only the interrupt lives here: a node restarts from its top on resume.
        interrupt({"stage": "report_ready"})
        return {}

    return {
        "prepare_cv": prepare_cv,
        "prepare_job": prepare_job,
        "plan_matching": plan_matching,
        "route_matching": route_matching,
        "match_chunk": match_chunk,
        "score_and_verdict": score_and_verdict,
        "await_optimize": await_optimize,
    }
