"""Assessments, score and verdict from state. Pure: also used when the user edits inputs."""

from backedcv.domain.builders import build_assessments
from backedcv.domain.models import (
    CandidateFacts,
    JobPosting,
    ParsedCV,
    PostingBanner,
    RequirementFlag,
)
from backedcv.domain.rules.absurd import flags_by_requirement
from backedcv.domain.rules.knockout import apply_facts
from backedcv.domain.scoring import compute_score
from backedcv.domain.verdict import compute_verdict
from backedcv.llm.drafts import AssessmentDraft


def recompute(state: dict) -> dict:
    job = JobPosting.model_validate(state["job"])
    cv = ParsedCV.model_validate(state["cv"])
    drafts = {
        rid: AssessmentDraft.model_validate(d)
        for rid, d in (state.get("assessment_drafts") or {}).items()
    }
    facts = CandidateFacts.model_validate(state.get("facts") or {})
    flags = [RequirementFlag.model_validate(f) for f in state.get("flags") or []]
    banners = [
        PostingBanner.model_validate(b)
        for b in [*(state.get("banners") or []), *(state.get("review_banners") or [])]
    ]
    flagged = flags_by_requirement(flags)
    excluded = set(state.get("excluded_ids") or [])
    included = set(state.get("included_flagged_ids") or [])

    assessments = build_assessments(job, cv, drafts)
    by_id = {r.id: r for r in job.requirements}
    assessments = {rid: apply_facts(by_id[rid], a, facts, job) for rid, a in assessments.items()}
    score = compute_score(
        job.requirements,
        assessments,
        excluded_ids=excluded,
        flagged=flagged,
        included_flagged_ids=included,
    )
    verdict = compute_verdict(
        job, assessments, score, flagged=flagged, included_flagged_ids=included, banners=banners
    )
    return {
        "assessments": {rid: a.model_dump() for rid, a in assessments.items()},
        "score": score.model_dump(),
        "verdict": verdict.model_dump(),
    }
