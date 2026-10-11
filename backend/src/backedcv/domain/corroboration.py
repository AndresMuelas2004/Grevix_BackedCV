"""Corroboration gate for suggested CV edits, and requirements whose edits are not viable.

Pass 1 ("backed") is the guards and the verifier that already ran. Passes 2 and 3 refuse an edit
as not viable: its evidence is too old for a stated recency window ("recent_enough"), or a hidden
barrier blocks its requirement ("not_blocked"). Everything here is pure: no model call, and the
date is a parameter.
"""

from collections.abc import Iterable
from datetime import date

from backedcv.domain.models import (
    ELIGIBILITY_KINDS,
    GatePass,
    HiddenRisk,
    JobPosting,
    RecencyCheck,
    Refusal,
    RequirementAssessment,
    RiskLevel,
    Suggestion,
)
from backedcv.domain.models.screening import join_sentences, short_sentence

STALE_AFTER_YEARS = 6.0  # the "stale" recency band, kept local on purpose
PASS_ORDER = ("backed", "recent_enough", "not_blocked")  # the order the gate runs the passes in


def requirement_risk(rid: str, risks: list[HiddenRisk]) -> RiskLevel | None:
    """The highest level among the requirement's unresolved risks. Two unresolved medium risks
    count as one high one. None when no unresolved risk lists the requirement."""
    levels = [r.risk for r in _open(rid, risks)]
    if not levels:
        return None
    if "high" in levels or levels.count("medium") >= 2:
        return "high"
    return "medium" if "medium" in levels else "low"


def not_viable_targets(
    job: JobPosting,
    assessments: dict[str, RequirementAssessment],
    recency: dict[str, RecencyCheck],
    risks: list[HiddenRisk],
    excluded: Iterable[str],
) -> list[Refusal]:
    """Requirements whose edits are refused before any edit is generated: their only evidence is
    outside a stated recency window, or a hidden barrier blocks a requirement the CV meets. The
    suggest step skips them. Requirements the candidate excluded are left out."""
    skipped = set(excluded)
    refusals: list[Refusal] = []
    for req in job.requirements:
        if req.id in skipped:
            continue
        check = recency.get(req.id)
        if check is not None and check.effect == "downgraded":
            refusals.append(
                Refusal(
                    requirement_id=req.id,
                    gate="recent_enough",
                    reason=_stale_reason(req.label, check),
                    refs=list(check.evidence_refs),
                )
            )
        assessment = assessments.get(req.id)
        if assessment is None or assessment.status not in ("met", "partial"):
            continue
        blocking = _blocking(req.id, risks)
        if blocking:
            refusals.append(
                Refusal(
                    requirement_id=req.id,
                    gate="not_blocked",
                    reason=_blocked_reason(blocking),
                    refs=_conflict_refs(blocking, assessment),
                )
            )
    return refusals


def backed_pass(s: Suggestion) -> GatePass:
    """Pass 1: the guards and the verifier already tie the edit to real CV lines. A refused edit
    was backed too, so it passes. An edit that never verified fails here, but apply_pass does not
    refuse it: it was not viable to begin with, only unsupported."""
    if s.verification.status in ("verified", "refused"):
        return GatePass(name="backed", ok=True)
    return GatePass(
        name="backed",
        ok=False,
        detail=s.verification.reason or "No real CV line backs this edit.",
    )


def recency_pass(
    s: Suggestion,
    recency: dict[str, RecencyCheck],
    last_used: dict[str, str],
    today: date,
) -> GatePass:
    """Pass 2: where the posting states a recency window for a target, a cited line (or the
    target line) must have been used inside it. Undated lines do not count. Without a window,
    cited lines that were all last used more than six years ago only get a note."""
    cited = [ref for ref in dict.fromkeys([*s.cited_refs, s.target]) if ref in last_used]
    windows: list[float] = []
    for rid in _targets(s):
        check = recency.get(rid)
        if check is not None and check.rule is not None:
            windows.append(check.rule.window_years)
    for window in windows:
        if not any(_years_since(last_used[ref], today) <= window for ref in cited):
            return GatePass(
                name="recent_enough",
                ok=False,
                detail=(
                    "Not viable: none of the cited lines shows use within the last "
                    f"{window:g} years."
                ),
            )
    dated = [_years_since(last_used[ref], today) for ref in cited]
    if not windows and dated and min(dated) > STALE_AFTER_YEARS:
        return GatePass(
            name="recent_enough",
            ok=True,
            hard=False,
            detail=f"All cited lines were last used more than {STALE_AFTER_YEARS:g} years ago.",
        )
    return GatePass(name="recent_enough", ok=True)


def barrier_pass(s: Suggestion, risks: list[HiddenRisk]) -> GatePass:
    """Pass 3: no target may be blocked by an eligibility barrier or by a composite risk."""
    for rid in _targets(s):
        blocking = _blocking(rid, risks)
        if blocking:
            return GatePass(name="not_blocked", ok=False, detail=_blocked_reason(blocking))
    return GatePass(name="not_blocked", ok=True)


def apply_pass(s: Suggestion, p: GatePass) -> Suggestion:
    """A copy of the suggestion with the pass recorded. Running a pass again replaces its earlier
    result, and the passes always stay in PASS_ORDER, so the outcome does not depend on the order
    the passes ran in. A verified or refused suggestion is refused while a hard pass fails (the
    first failing detail is the reason), and verified again once none does. Other statuses are
    left alone."""
    kept = [q for q in s.verification.passes if q.name != p.name]
    passes = sorted([*kept, p], key=lambda q: PASS_ORDER.index(q.name))
    verification = s.verification.model_copy(update={"passes": passes})
    if s.verification.status in ("verified", "refused"):
        failing = next((q for q in passes if not q.ok and q.hard), None)
        if failing is None:
            update = {"status": "verified", "reason": None}
        else:
            update = {"status": "refused", "reason": failing.detail}
        verification = verification.model_copy(update=update)
    return s.model_copy(update={"verification": verification})


def refusals_from(suggestions: list[Suggestion]) -> list[Refusal]:
    """One refusal per refused suggestion: the first requirement it targets, the gate that refused
    it, and the lines it cites."""
    refusals: list[Refusal] = []
    for s in suggestions:
        targets = _targets(s)
        failed = next(
            (p for p in s.verification.passes if not p.ok and p.hard and p.name != "backed"),
            None,
        )
        if s.verification.status != "refused" or failed is None or not targets:
            continue
        gate = "recent_enough" if failed.name == "recent_enough" else "not_blocked"
        refusals.append(
            Refusal(
                requirement_id=targets[0],
                gate=gate,
                reason=failed.detail or "Not viable.",
                refs=list(s.cited_refs),
                suggestion_id=s.id,
            )
        )
    return refusals


def _targets(s: Suggestion) -> list[str]:
    """The requirements an edit is for: the ones the model names, then the ones its text covers."""
    return list(dict.fromkeys([*s.requirement_ids, *s.covers_requirement_ids]))


def _open(rid: str, risks: list[HiddenRisk]) -> list[HiddenRisk]:
    return [r for r in risks if rid in r.requirement_ids and not r.resolved]


def _blocking(rid: str, risks: list[HiddenRisk]) -> list[HiddenRisk]:
    """The unresolved risks that make the requirement high from an eligibility kind or a composite.
    Same rule as requirement_risk, but only eligibility and composite risks count. Empty if none."""
    own = [r for r in _open(rid, risks) if r.kind in ELIGIBILITY_KINDS or r.kind == "composite"]
    if sum(r.risk == "medium" for r in own) >= 2:
        return [r for r in own if r.risk != "low"]
    return [r for r in own if r.risk == "high"]


def _years_since(ym: str, today: date) -> float:
    """Years from a YYYY-MM date to today, months / 12 to one decimal (as years_since does)."""
    year, month = (int(part) for part in ym.split("-"))
    return round(((today.year - year) * 12 + today.month - month) / 12, 1)


def _stale_reason(label: str, check: RecencyCheck) -> str:
    span = f"the last {check.rule.window_years:g} years" if check.rule else "the stated window"
    if check.last_used:
        return f"Not viable: {label} was last used in {check.last_used[:4]}, outside {span}."
    return f"Not viable: the evidence for {label} is outside {span}."


def _blocked_reason(blocking: list[HiddenRisk]) -> str:
    """The refusal for a hidden barrier, written from the first risk's own words: short
    sentences, no raw IDs, each ending with a full stop."""
    why = next((short_sentence(r.explanation) for r in blocking if r.explanation.strip()), "")
    advice = "A CV edit cannot fix this."
    if any(r.question and not r.confirmed for r in blocking):
        advice = "A CV edit cannot fix this; answer the question instead."
    return "Not viable: " + join_sentences(
        why or "a hidden barrier in the posting rules this out", advice
    )


def _conflict_refs(blocking: list[HiddenRisk], assessment: RequirementAssessment) -> list[str]:
    refs = list(dict.fromkeys(ref for r in blocking for ref in r.cv_refs))
    return refs or [e.ref for e in assessment.evidence]
