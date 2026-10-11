"""Rule-based verdict: knockouts first, then score bands. The first matching rule wins."""

from backedcv.domain.models import (
    ELIGIBILITY_KINDS,
    Contribution,
    HiddenRisk,
    JobPosting,
    PostingBanner,
    RequirementAssessment,
    ScoreBreakdown,
    Verdict,
    VerdictReason,
)
from backedcv.domain.rules.knockout import is_knockout, likely_question
from backedcv.domain.scoring import ScoringConfig, round_half_up

TITLES = {
    "likely_screened_out": "Likely screened out",
    "apply": "Apply",
    "stretch": "Stretch: apply if you can explain the gaps",
    "long_shot": "Long shot",
}
NAMED_LIMIT = 3  # most requirements that one reason names


def compute_verdict(
    job: JobPosting,
    assessments: dict[str, RequirementAssessment],
    score: ScoreBreakdown,
    *,
    flagged: dict[str, str] | None = None,
    included_flagged_ids: set[str] | None = None,
    banners: list[PostingBanner] | None = None,
    config: ScoringConfig | None = None,
    hidden_risks: list[HiddenRisk] | None = None,
) -> Verdict:
    config = config or ScoringConfig.default()
    flagged = flagged or {}
    included = included_flagged_ids or set()
    excluded = {
        c.requirement_id for c in score.contributions if c.excluded_reason == "not_relevant"
    }

    def status(req_id: str) -> str:
        a = assessments.get(req_id)
        return a.status if a else "unknown"

    knockouts = [r for r in job.requirements if is_knockout(r) and r.id not in excluded]
    active = [r for r in knockouts if r.id not in flagged or r.id in included]
    flagged_knockouts = [r for r in knockouts if r.id in flagged and r.id not in included]

    risks = _counted_risks(job, hidden_risks or [])
    failed = [r for r in risks if _is_failed(r)]
    unanswered = [r for r in risks if _is_unanswered(r)]
    notes = [_note(r) for r in risks if _is_note(r)]

    badges = []
    if (
        score.fit is not None
        and score.coverage is not None
        and score.fit - score.coverage >= config.tailor_first_gap
    ):
        badges.append("tailor_first")
    if any(status(r.id) == "missing" for r in flagged_knockouts):
        badges.append("screening_risk")
    if banners:
        badges.append("posting_red_flags")

    missing = [r for r in active if status(r.id) == "missing"]
    if missing or failed:
        return Verdict(
            label="likely_screened_out",
            title=TITLES["likely_screened_out"],
            badges=badges,
            reasons=[
                VerdictReason(
                    text=_would_reject(f'"{r.quote}"'),
                    requirement_ids=[r.id],
                )
                for r in missing
            ]
            + [
                VerdictReason(
                    text=_would_reject(f'"{r.quote}"' if r.quote else "This hidden barrier"),
                    requirement_ids=list(r.requirement_ids),
                )
                for r in failed
            ]
            + notes,
        )

    band, band_reasons = _band(job, assessments, score, excluded, flagged, included, config)
    unknown = [r for r in active if status(r.id) == "unknown"]
    if unknown or unanswered:
        n = len(unknown) + len(unanswered)
        return Verdict(
            label="answer_questions",
            title=f"Answer {n} question{'s' if n != 1 else ''} first",
            badges=badges,
            reasons=[
                VerdictReason(
                    text=(assessments.get(r.id) and assessments[r.id].question)
                    or likely_question(r, job),
                    requirement_ids=[r.id],
                )
                for r in unknown
            ]
            + [
                VerdictReason(text=r.question or "", requirement_ids=list(r.requirement_ids))
                for r in unanswered
            ]
            + band_reasons
            + notes,
            provisional=True,
        )

    return Verdict(label=band, title=TITLES[band], badges=badges, reasons=band_reasons + notes)


def _would_reject(subject: str) -> str:
    return (
        f"{subject}: if the employer asks this as a screening question, "
        "your answer would likely reject the application."
    )


def _counted_risks(job: JobPosting, risks: list[HiddenRisk]) -> list[HiddenRisk]:
    """The risks that may change the verdict. A risk that lists a knockout never does: the
    knockout's own question already covers it."""
    knockouts = {r.id for r in job.requirements if r.knockout_type is not None}
    return [r for r in risks if knockouts.isdisjoint(r.requirement_ids)]


def _is_failed(r: HiddenRisk) -> bool:
    """A confirmed eligibility barrier (answered no): it acts as a failed knockout."""
    return r.confirmed and not r.resolved and r.kind in ELIGIBILITY_KINDS


def _is_unanswered(r: HiddenRisk) -> bool:
    """A high risk with a question nobody has answered: one more unanswered knockout."""
    return r.risk == "high" and bool(r.question) and not r.resolved and not r.confirmed


def _is_note(r: HiddenRisk) -> bool:
    """Any other unresolved high risk, composites included: it adds one reason and no question."""
    return r.risk == "high" and not r.resolved and not _is_failed(r) and not _is_unanswered(r)


def _note(r: HiddenRisk) -> VerdictReason:
    return VerdictReason(
        text=f"Hidden screening risk: {r.explanation or r.quote}",
        requirement_ids=list(r.requirement_ids),
    )


def _band(job, assessments, score, excluded, flagged, included, config):
    if score.fit is None:
        return "stretch", [VerdictReason(text="No scorable requirements were found.")]

    blocking = [
        r
        for r in job.requirements
        if r.importance == "required"
        and r.id not in excluded
        and (r.id not in flagged or r.id in included)
        and config.category_weights.get(r.category, 1) >= config.blocking_min_category_weight
        and (assessments.get(r.id) is not None and assessments[r.id].status == "missing")
    ]
    reasons = [_fit_reason(score.fit, config)]
    if score.fit >= config.apply_min_fit and not blocking:
        matches = _heaviest(score, "met")
        if matches:
            reasons.append(_named("Strongest matches", matches))
        return "apply", reasons
    missing = _heaviest(score, "missing", importance="required")
    if missing:
        reasons.append(_named("Missing required", missing))
    band = "stretch" if score.fit >= config.stretch_min_fit else "long_shot"
    return band, reasons


def _fit_reason(fit: float, config: ScoringConfig) -> VerdictReason:
    """The Fit value next to the two thresholds, so every band can be read against them."""
    return VerdictReason(
        text=(
            f"Your Fit is {round_half_up(fit)} out of 100; "
            f"{round_half_up(config.stretch_min_fit)} is needed for a stretch "
            f"and {round_half_up(config.apply_min_fit)} to apply with confidence."
        )
    )


def _heaviest(
    score: ScoreBreakdown, status: str, importance: str | None = None
) -> list[Contribution]:
    """Up to NAMED_LIMIT counted requirements with this status, heaviest first. Sorting is
    stable, so ties keep the order of the posting."""
    rows = [
        c
        for c in score.contributions
        if c.excluded_reason is None
        and c.status == status
        and (importance is None or c.importance == importance)
    ]
    return sorted(rows, key=lambda c: -c.weight)[:NAMED_LIMIT]


def _named(lead: str, rows: list[Contribution]) -> VerdictReason:
    return VerdictReason(
        text=f"{lead}: " + ", ".join(c.label for c in rows) + ".",
        requirement_ids=[c.requirement_id for c in rows],
    )
