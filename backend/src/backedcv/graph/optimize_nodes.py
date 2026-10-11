"""Optimize-phase nodes: suggest rewrites, verify each one, then pause for the user's review."""

import logging
from collections.abc import Callable
from typing import TypedDict

from langgraph.types import Send, interrupt

from backedcv.domain.corroboration import (
    apply_pass,
    backed_pass,
    barrier_pass,
    not_viable_targets,
    recency_pass,
    refusals_from,
)
from backedcv.domain.guards import NEW_SKILLS, NEW_SUMMARY, apply_guards, keyword_only
from backedcv.domain.models import (
    ClaimCheck,
    JobPosting,
    ParsedCV,
    Requirement,
    RequirementAssessment,
    ReviewDecisions,
    Suggestion,
)
from backedcv.domain.models.suggestion import VerificationStatus
from backedcv.domain.recency import line_last_used
from backedcv.domain.redaction import numbered_rows
from backedcv.graph.nodes import _error, _progress
from backedcv.graph.recompute import assessments_of, recency_of, risks_of, today_of
from backedcv.graph.state import AnalysisState
from backedcv.llm.drafts_optimize import (
    ClaimDraft,
    SuggestionDraft,
    SuggestionsDraft,
    VerificationBatchDraft,
    VerificationDraft,
)
from backedcv.llm.prompt_loader import load_prompt
from backedcv.llm.structured import StructuredLLM

log = logging.getLogger(__name__)


class VerifyTask(TypedDict):
    """Payload of one verify_batch call: one CV section's pending suggestions, and the whole CV."""

    cv: dict
    group: list[dict]  # not "suggestions": a TypedDict input schema must not clash with the state


def _cv_block(cv: ParsedCV) -> str:
    """The CV lines and computed facts that suggest and verify read, with contact data redacted."""
    lines = cv.numbered(include_facts=False)
    facts = numbered_rows((fact.id, fact.text) for fact in cv.facts)
    return f"<cv_lines>\n{lines}\n</cv_lines>\n\n<facts>\n{facts}\n</facts>"


def _needs_wording(req: Requirement, a: RequirementAssessment | None, excluded: set[str]) -> bool:
    """Met by evidence, but the posting's exact terms are missing from the CV."""
    return (
        req.id not in excluded
        and a is not None
        and a.status == "met"
        and bool(a.evidence)
        and not a.keyword_present
        and bool(req.terms)
    )


def _requirement_row(req: Requirement, a: RequirementAssessment) -> str:
    terms = ", ".join(f'"{term}"' for term in req.terms)
    evidence = ", ".join(e.ref for e in a.evidence)
    return f"{req.id} | terms: {terms} | evidence: {evidence}"


def _suggestion_row(s: Suggestion) -> str:
    cited = ", ".join(s.cited_refs)
    introduced = ", ".join(s.introduced_terms) or "none"
    after = " ".join(s.after.split())  # one row per suggestion, even when `after` has newlines
    return f"{s.id} | cited: {cited} | introduced: {introduced} | after: {after}"


def _suggested_after(d: SuggestionDraft) -> str:
    """Skill names start with a capital, so "vector databases" reads "Vector databases" under
    Skills. A first word that already has a capital ("iOS") keeps its casing. Other kinds keep
    the model's wording."""
    first_word = d.after.partition(" ")[0]
    if d.kind != "add_skill" or first_word != first_word.lower():
        return d.after
    return d.after[:1].upper() + d.after[1:]


def _suggest_target(d: SuggestionDraft, cv: ParsedCV) -> str:
    """Maps the heading or line IDs the model gives onto the section IDs the app uses."""
    if d.kind == "align_wording":
        return d.target
    if d.kind == "tailor_summary":
        summary = next((s for s in cv.sections if s.type == "summary"), None)
        return summary.id if summary else NEW_SUMMARY
    section_of = {line_id: s for s in cv.sections for line_id in s.line_ids}
    for ref in [d.target, *d.cited_refs]:
        section = section_of.get(ref)
        if section is not None and section.type == "skills":
            return section.id
    skills = next((s for s in cv.sections if s.type == "skills"), None)
    return skills.id if skills else NEW_SKILLS


def _drop_padding(suggestions: list[Suggestion], job: JobPosting) -> list[Suggestion]:
    """The model's suggestions without the ones that only pad their line with posting words or
    filler, numbered S01, S02... in their order. Padding is backed by the CV, so it is dropped
    rather than marked unsupported, and it never costs a verifier call."""
    kept: list[Suggestion] = []
    for s in suggestions:
        reason = keyword_only(s, job)
        if reason is None:
            kept.append(s)
        else:
            log.info("suggest dropped a %s edit of %s: %s", s.kind, s.target, reason)
    return [s.model_copy(update={"id": f"S{i:02d}"}) for i, s in enumerate(kept, start=1)]


def _section_of(target: str, cv: ParsedCV) -> str:
    """The CV section a suggestion's target sits in. A target outside every section stands alone."""
    for section in cv.sections:
        if target in (section.id, *section.line_ids):
            return section.id
    return target


def _stored_suggestions(state: AnalysisState) -> list[Suggestion]:
    return [Suggestion.model_validate(row) for row in state.get("suggestions") or []]


def _claim_check(claim: ClaimDraft, refs: dict[str, str]) -> ClaimCheck:
    known = [ref for ref in claim.supported_by if ref in refs]
    unknown = [ref for ref in claim.supported_by if ref not in refs]
    reason = claim.unsupported_reason or None
    if unknown:
        reason = f"cites IDs that are not in the CV: {', '.join(unknown)}"
    elif not known:
        reason = reason or "no CV line or fact shows it"
    return ClaimCheck(text=claim.text, supported_by=known, ok=reason is None, reason=reason)


def _with_verification(
    s: Suggestion, status: VerificationStatus, reason: str | None, claims: list[ClaimCheck]
) -> Suggestion:
    verification = s.verification.model_copy(
        update={"status": status, "reason": reason, "claims": claims}
    )
    return s.model_copy(update={"verification": verification})


def _verdict(s: Suggestion, answer: VerificationDraft | None, cv: ParsedCV) -> Suggestion:
    """Verified only if every hard guard, claim and term passes and the verifier is sure."""
    if answer is None:
        return _with_verification(s, "unsupported", "not verified", [])
    refs = cv.texts_by_ref()
    claims = [_claim_check(c, refs) for c in answer.claims]
    reasons = [g.detail or g.name for g in s.verification.guards if g.hard and not g.ok]
    reasons += [c.reason for c in claims if c.reason]
    reasons += [
        f"adds a claim: {t.term}" for t in answer.term_judgements if t.verdict == "adds_claim"
    ]
    if answer.uncertain or not claims:
        reasons.append("the verifier was not sure")
    if reasons:
        return _with_verification(s, "unsupported", reasons[0], claims)
    return _with_verification(s, "verified", None, claims)


def make_optimize_nodes(llm: StructuredLLM) -> dict[str, Callable]:
    async def suggest(state: AnalysisState) -> dict:
        _progress("suggest", "started")
        cv = ParsedCV.model_validate(state["cv"])
        job = JobPosting.model_validate(state["job"])
        excluded = set(state.get("excluded_ids") or [])
        assessments = assessments_of(state)
        # Requirements that are not viable (too old, or blocked by a hidden barrier) get no wording.
        held = not_viable_targets(job, assessments, recency_of(state), risks_of(state), excluded)
        skipped = excluded | {refusal.requirement_id for refusal in held}
        rows = [
            _requirement_row(req, assessments[req.id])
            for req in job.requirements
            if _needs_wording(req, assessments.get(req.id), skipped)
        ]
        if not rows:
            _progress("suggest", "done", suggestions=0)
            return {"suggestions": []}
        requirements = "\n".join(rows)
        data = f"{_cv_block(cv)}\n\n<requirements>\n{requirements}\n</requirements>"
        try:
            draft, usage = await llm.run(
                load_prompt("suggest"), data, SuggestionsDraft, node="suggest"
            )
        except Exception as exc:  # suggestions are optional: the report stands without them
            _progress("suggest", "done", suggestions=0)
            return {"suggestions": [], "errors": [_error("suggest", exc)]}
        guarded = [
            apply_guards(
                Suggestion(
                    id=f"S{i:02d}",
                    kind=d.kind,
                    target=_suggest_target(d, cv),
                    after=_suggested_after(d),
                    requirement_ids=d.requirement_ids,
                    cited_refs=d.cited_refs,
                ),
                cv,
                job,
            )
            for i, d in enumerate(draft.suggestions, start=1)
        ]
        suggestions = [s.model_dump() for s in _drop_padding(guarded, job)]
        _progress("suggest", "done", suggestions=len(suggestions))
        return {"suggestions": suggestions, "usage": [usage]}

    def route_verification(state: AnalysisState) -> list[Send] | str:
        suggestions = [Suggestion.model_validate(s) for s in state.get("suggestions") or []]
        pending = [s for s in suggestions if s.verification.status == "pending"]
        if not pending:
            return "gate_recency"  # an empty Send list would end the graph early
        cv = ParsedCV.model_validate(state["cv"])
        groups: dict[str, list[dict]] = {}
        for s in pending:
            groups.setdefault(_section_of(s.target, cv), []).append(s.model_dump())
        return [
            Send("verify_batch", VerifyTask(cv=state["cv"], group=rows)) for rows in groups.values()
        ]

    async def verify_batch(task: VerifyTask) -> dict:
        _progress("verify", "started")
        cv = ParsedCV.model_validate(task["cv"])
        suggestions = [Suggestion.model_validate(s) for s in task["group"]]
        rows = "\n".join(_suggestion_row(s) for s in suggestions)
        data = f"{_cv_block(cv)}\n\n<suggestions>\n{rows}\n</suggestions>"
        try:
            batch, usage = await llm.run(
                load_prompt("verify"), data, VerificationBatchDraft, node="verify_batch"
            )
        except Exception as exc:  # no answer is no proof: the whole group is unsupported
            _progress("verify", "done", suggestions=len(suggestions))
            failed = [
                _with_verification(s, "unsupported", "verification failed", []) for s in suggestions
            ]
            return {
                "suggestions": [s.model_dump() for s in failed],
                "errors": [_error("verify_batch", exc)],
            }
        answers = {v.suggestion_id: v for v in batch.verifications}
        checked = [_verdict(s, answers.get(s.id), cv) for s in suggestions]
        _progress("verify", "done", suggestions=len(checked))
        return {"suggestions": [s.model_dump() for s in checked], "usage": [usage]}

    async def gate_recency(state: AnalysisState) -> dict:
        """Every suggestion must pass the backed check, then the recency check. No model call."""
        today = today_of(state)
        cv = ParsedCV.model_validate(state["cv"])
        last_used = line_last_used(cv, today)
        recency = recency_of(state)
        rows = []
        for s in _stored_suggestions(state):
            s = apply_pass(s, backed_pass(s))
            s = apply_pass(s, recency_pass(s, recency, last_used, today))
            rows.append(s.model_dump())
        return {"suggestions": rows}

    async def gate_barriers(state: AnalysisState) -> dict:
        """The barrier check on every suggestion, then the refusals: requirements not viable from
        the start, and every suggestion refused by a gate."""
        job = JobPosting.model_validate(state["job"])
        assessments = assessments_of(state)
        recency = recency_of(state)
        risks = risks_of(state)
        excluded = set(state.get("excluded_ids") or [])
        rows = [apply_pass(s, barrier_pass(s, risks)) for s in _stored_suggestions(state)]
        refusals = [
            *not_viable_targets(job, assessments, recency, risks, excluded),
            *refusals_from(rows),
        ]
        return {
            "suggestions": [s.model_dump() for s in rows],
            "refusals": [r.model_dump() for r in refusals],
        }

    async def await_review(state: AnalysisState) -> dict:
        # Nothing runs before the interrupt: a node restarts from its top on resume.
        decisions = ReviewDecisions.model_validate(interrupt({"stage": "review_ready"}))
        return {"decisions": decisions.model_dump()}

    return {
        "suggest": suggest,
        "route_verification": route_verification,
        "verify_batch": verify_batch,
        "gate_recency": gate_recency,
        "gate_barriers": gate_barriers,
        "await_review": await_review,
    }
