"""Assessments, score, verdict and the Card 1 screening results from state. Pure: also used when the
user edits inputs. Older states (no Card 1 keys) work: the missing keys count as empty."""

from datetime import date, datetime

from backedcv.domain.barriers import (
    assess_risks,
    find_rule_barriers,
    merge_barriers,
    screening_flags,
)
from backedcv.domain.builders import build_assessments
from backedcv.domain.corroboration import not_viable_targets
from backedcv.domain.models import (
    BarrierItem,
    CandidateFacts,
    HiddenRisk,
    JobPosting,
    ParsedCV,
    PostingBanner,
    RecencyCheck,
    RecencyRule,
    RequirementAssessment,
    RequirementFlag,
)
from backedcv.domain.recency import apply_recency, check_recency, find_recency_rules
from backedcv.domain.rules.absurd import flags_by_requirement
from backedcv.domain.rules.knockout import apply_facts
from backedcv.domain.scoring import compute_score
from backedcv.domain.verdict import compute_verdict
from backedcv.llm.drafts import AssessmentDraft


def today_of(state: dict) -> date:
    """The analysis date: the day the analysis was created, so every later check agrees with it."""
    created = state.get("created_at")
    if created:
        try:
            return datetime.fromisoformat(created).date()
        except ValueError:
            pass
    return date.today()


def assessments_of(state: dict) -> dict[str, RequirementAssessment]:
    return {
        rid: RequirementAssessment.model_validate(a)
        for rid, a in (state.get("assessments") or {}).items()
    }


def recency_of(state: dict) -> dict[str, RecencyCheck]:
    return {rid: RecencyCheck.model_validate(c) for rid, c in (state.get("recency") or {}).items()}


def risks_of(state: dict) -> list[HiddenRisk]:
    return [HiddenRisk.model_validate(r) for r in state.get("hidden_risks") or []]


def _model_windows(barriers: list[BarrierItem]) -> list[RecencyRule]:
    """The recency windows the model found, as rules the CV is checked against too. Code rules are
    not repeated here. Read from the merged barriers: merge_barriers has already given a model item
    that shares its sentence with a code rule that rule's window, so every later run agrees."""
    return [
        RecencyRule(
            quote=item.quote,
            window_years=item.window_years,
            requirement_ids=list(item.requirement_ids),
            source="model",
        )
        for item in barriers
        if item.kind == "recency" and item.source == "model" and item.window_years is not None
    ]


def _shared_answers(
    facts: CandidateFacts, barriers: list[BarrierItem], job: JobPosting
) -> CandidateFacts:
    """One answer per fact. A barrier tied to a gate requirement asks no question of its own (the
    requirement asks), so an answer saved under the barrier's ID (before the two were linked)
    answers the requirement too. An answer saved under the requirement's ID always wins."""
    gates = {r.id for r in job.requirements if r.knockout_type is not None}
    answers = dict(facts.answers)
    for barrier in barriers:
        answer = facts.answers.get(barrier.id)
        if answer is None:
            continue
        for rid in barrier.requirement_ids:
            if rid in gates:
                answers.setdefault(rid, answer)
    if answers == facts.answers:
        return facts
    return facts.model_copy(update={"answers": answers})


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
    today = today_of(state)

    job_text = state.get("job_text") or ""
    code_rules = find_recency_rules(job_text, job)
    model_items = [BarrierItem.model_validate(b) for b in state.get("barrier_items") or []]
    barriers = merge_barriers(model_items, find_rule_barriers(job_text), code_rules, job)
    rules = [*code_rules, *_model_windows(barriers)]
    facts = _shared_answers(facts, barriers, job)

    by_id = {r.id: r for r in job.requirements}
    original = build_assessments(job, cv, drafts)
    original = {rid: apply_facts(by_id[rid], a, facts, job) for rid, a in original.items()}
    checks = check_recency(job, cv, original, rules, today)
    assessments = apply_recency(original, checks)
    risks = assess_risks(barriers, job, cv, assessments, facts, checks)
    flags_out = screening_flags(job, original, checks, risks)

    score = compute_score(
        job.requirements,
        assessments,
        excluded_ids=excluded,
        flagged=flagged,
        included_flagged_ids=included,
    )
    verdict = compute_verdict(
        job,
        assessments,
        score,
        flagged=flagged,
        included_flagged_ids=included,
        banners=banners,
        hidden_risks=risks,
        recency=checks,
    )
    refusals = not_viable_targets(job, assessments, checks, risks, excluded)
    return {
        "assessments": {rid: a.model_dump() for rid, a in assessments.items()},
        "score": score.model_dump(),
        "verdict": verdict.model_dump(),
        "barrier_items": [b.model_dump() for b in barriers],
        "recency": {rid: c.model_dump() for rid, c in checks.items()},
        "hidden_risks": [r.model_dump() for r in risks],
        "screening_flags": [f.model_dump() for f in flags_out],
        "refusals": [r.model_dump() for r in refusals],
    }
