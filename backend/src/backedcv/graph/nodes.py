"""Graph nodes. Each LLM node degrades gracefully where the feature is optional."""

import contextlib
import logging
from datetime import date

from langgraph.config import get_stream_writer
from langgraph.types import Send, interrupt

from backedcv.domain.barriers import barriers_from_draft
from backedcv.domain.builders import build_job, build_parsed_cv
from backedcv.domain.keywords import keyword_hits
from backedcv.domain.models import CVLine, JobPosting, ParsedCV, PostingBanner
from backedcv.domain.parse_checks import run_parse_checks
from backedcv.domain.recruiter_tips import recruiter_tips
from backedcv.domain.redaction import numbered_rows
from backedcv.domain.rules.absurd import flag_requirements
from backedcv.domain.rules.posting import tool_sprawl_banner
from backedcv.domain.text import fold_lower
from backedcv.graph.recompute import recompute
from backedcv.graph.state import AnalysisState, MatchTask
from backedcv.llm.drafts import CVStructureDraft, JobExtractionDraft, MatchChunkDraft
from backedcv.llm.drafts_optimize import PostingReviewDraft
from backedcv.llm.drafts_screening import HiddenBarriersDraft
from backedcv.llm.prompt_loader import load_prompt
from backedcv.llm.structured import StructuredLLM

log = logging.getLogger(__name__)
CHUNK_SIZE = 8
META_FIELDS = (
    "title",
    "company",
    "seniority",
    "seniority_quote",
    "location",
    "remote_policy",
    "employment_type",
)


def _progress(step: str, status: str, **extra) -> None:
    # Outside a streaming run (direct calls in tests) there is no writer.
    with contextlib.suppress(RuntimeError):
        get_stream_writer()({"type": "progress", "step": step, "status": status, **extra})


def _error(node: str, exc: Exception) -> dict:
    log.warning("node %s failed: %s", node, exc)
    return {"node": node, "error": type(exc).__name__, "detail": str(exc)[:300]}


def _review_data(job: JobPosting) -> str:
    """The posting as the review prompt reads it: one `field: value` line each, then the rows."""
    meta = "\n".join(f"{field}: {getattr(job, field) or 'none'}" for field in META_FIELDS)
    rows = "\n".join(f"{req.id} | {req.quote}" for req in job.requirements)
    return f"<job_meta>\n{meta}\n</job_meta>\n\n<requirements>\n{rows}\n</requirements>"


def _review_banners(draft: PostingReviewDraft, job: JobPosting) -> list[PostingBanner]:
    """R4 banners. Findings without a quote or a credential name are dropped."""
    banners: list[PostingBanner] = []
    for item in draft.contradictions:
        quotes = [q.strip() for q in item.quotes if q.strip()]
        if not quotes or not item.explanation.strip():
            continue
        shown = " / ".join(f'"{q}"' for q in quotes)
        banners.append(
            PostingBanner(
                rule_id="R4",
                requirement_ids=_requirements_quoting(job, quotes),
                severity="info",
                explanation=f"{item.explanation.strip()} Posting text: {shown}",
            )
        )
    for item in draft.doubtful_credentials:
        name = item.credential.strip()
        if not name or not item.explanation.strip():
            continue
        banners.append(
            PostingBanner(
                rule_id="R4",
                requirement_ids=_requirements_quoting(job, [name]),
                severity="info",
                explanation=f'"{name}": {item.explanation.strip()}',
            )
        )
    return banners


def _barrier_data(posting: str, job: JobPosting) -> str:
    """The posting as written, then its requirement rows: barriers name the IDs they affect."""
    rows = "\n".join(f"{req.id} | {req.quote}" for req in job.requirements)
    return f"<job_posting>\n{posting}\n</job_posting>\n\n<requirements>\n{rows}\n</requirements>"


def _requirements_quoting(job: JobPosting, texts: list[str]) -> list[str]:
    folded = [fold_lower(text) for text in texts]
    return [req.id for req in job.requirements if any(t in fold_lower(req.quote) for t in folded)]


def make_nodes(llm: StructuredLLM):
    async def prepare_cv(state: AnalysisState) -> dict:
        _progress("prepare_cv", "started")
        lines = [CVLine.model_validate(row) for row in state["cv_lines"]]
        numbered = numbered_rows((line.id, line.text) for line in lines)
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
        meta = state.get("cv_meta") or {}
        parse_warnings = [
            *run_parse_checks(
                cv, multi_column=bool(meta.get("multi_column")), file_size=meta.get("size")
            ),
            *recruiter_tips(cv),
        ]
        _progress("prepare_cv", "done")
        return {
            **update,
            "cv": cv.model_dump(),
            "parse_warnings": [w.model_dump() for w in parse_warnings],
        }

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
        sprawl = tool_sprawl_banner(job)
        _progress("prepare_job", "done", requirements=len(job.requirements))
        return {
            "job": job.model_dump(),
            "job_notes": notes,
            "flags": [f.model_dump() for f in flags],
            "banners": [sprawl.model_dump()] if sprawl else [],
            "usage": [usage],
        }

    async def review_posting(state: AnalysisState) -> dict:
        # Same superstep as plan_matching, so score_and_verdict always reads its banners.
        # No progress event: the frontend shows a fixed list of steps.
        job = JobPosting.model_validate(state["job"])
        try:
            draft, usage = await llm.run(
                load_prompt("review_posting"),
                _review_data(job),
                PostingReviewDraft,
                node="review_posting",
            )
        except Exception as exc:  # the review is optional: the report stands without it
            return {"review_banners": [], "errors": [_error("review_posting", exc)]}
        banners = _review_banners(draft, job)
        return {"review_banners": [b.model_dump() for b in banners], "usage": [usage]}

    async def screen_barriers(state: AnalysisState) -> dict:
        # Same superstep as plan_matching, so score_and_verdict always reads the barriers.
        # No progress event: the frontend shows a fixed list of steps.
        posting = state["job_text"]
        job = JobPosting.model_validate(state["job"])
        try:
            draft, usage = await llm.run(
                load_prompt("hidden_barriers"),
                _barrier_data(posting, job),
                HiddenBarriersDraft,
                node="screen_barriers",
            )
            items = barriers_from_draft(draft, posting, job)
        except Exception as exc:  # the screen is optional: the rule barriers still stand
            return {"barrier_items": [], "errors": [_error("screen_barriers", exc)]}
        return {"barrier_items": [b.model_dump() for b in items], "usage": [usage]}

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
        "review_posting": review_posting,
        "screen_barriers": screen_barriers,
        "plan_matching": plan_matching,
        "route_matching": route_matching,
        "match_chunk": match_chunk,
        "score_and_verdict": score_and_verdict,
        "await_optimize": await_optimize,
    }
