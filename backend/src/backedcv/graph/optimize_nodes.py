"""Optimize-phase nodes: suggest rewrites, verify each one, then pause for the user's review."""

from collections.abc import Callable
from typing import TypedDict

from langgraph.types import Send, interrupt

from backedcv.domain.guards import NEW_SKILLS, NEW_SUMMARY, apply_guards
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
from backedcv.graph.nodes import _error, _progress
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


class VerifyTask(TypedDict):
    """Payload of one verify_batch call: one CV section's pending suggestions, and the whole CV."""

    cv: dict
    group: list[dict]  # not "suggestions": a TypedDict input schema must not clash with the state


def _cv_block(cv: ParsedCV) -> str:
    lines = cv.numbered(include_facts=False)
    facts = "\n".join(f"{fact.id} | {fact.text}" for fact in cv.facts)
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


def _section_of(target: str, cv: ParsedCV) -> str:
    """The CV section a suggestion's target sits in. A target outside every section stands alone."""
    for section in cv.sections:
        if target in (section.id, *section.line_ids):
            return section.id
    return target


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
        assessments = {
            rid: RequirementAssessment.model_validate(a)
            for rid, a in (state.get("assessments") or {}).items()
        }
        rows = [
            _requirement_row(req, assessments[req.id])
            for req in job.requirements
            if _needs_wording(req, assessments.get(req.id), excluded)
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
        suggestions = [
            apply_guards(
                Suggestion(
                    id=f"S{i:02d}",
                    kind=d.kind,
                    target=_suggest_target(d, cv),
                    after=d.after,
                    requirement_ids=d.requirement_ids,
                    cited_refs=d.cited_refs,
                ),
                cv,
                job,
            ).model_dump()
            for i, d in enumerate(draft.suggestions, start=1)
        ]
        _progress("suggest", "done", suggestions=len(suggestions))
        return {"suggestions": suggestions, "usage": [usage]}

    def route_verification(state: AnalysisState) -> list[Send] | str:
        suggestions = [Suggestion.model_validate(s) for s in state.get("suggestions") or []]
        pending = [s for s in suggestions if s.verification.status == "pending"]
        if not pending:
            return "await_review"  # an empty Send list would end the graph early
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

    async def await_review(state: AnalysisState) -> dict:
        # Nothing runs before the interrupt: a node restarts from its top on resume.
        decisions = ReviewDecisions.model_validate(interrupt({"stage": "review_ready"}))
        return {"decisions": decisions.model_dump()}

    return {
        "suggest": suggest,
        "route_verification": route_verification,
        "verify_batch": verify_batch,
        "await_review": await_review,
    }
