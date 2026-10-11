"""Rule-based verdict: knockouts first, then score bands. The first matching rule wins.

Hard dealbreakers apart from soft ones, so nobody self-rejects from a flexible role. Only a legal
knockout the CV shows missing (work authorization, clearance, a license to practise), a confirmed
eligibility barrier or a "no" answer makes the verdict "Likely screened out". A missing language,
education or experience knockout is a top risk that caps the band at Long shot; minimum years the
CV's own dates fall short of cap it at Stretch with at least 75% of the years, Long shot below.
Location and availability are asked, never asserted (see builders). Every reason is one short
sentence without raw IDs.
"""

from backedcv.domain.models import (
    ELIGIBILITY_KINDS,
    Contribution,
    HiddenRisk,
    JobPosting,
    PostingBanner,
    RecencyCheck,
    Requirement,
    RequirementAssessment,
    ScoreBreakdown,
    Verdict,
    VerdictReason,
)
from backedcv.domain.models.screening import clean_prose, short_sentence
from backedcv.domain.rules.knockout import (
    asks_min_years,
    is_knockout,
    likely_question,
    years_sentence,
)
from backedcv.domain.scoring import ScoringConfig, round_half_up

TITLES = {
    "likely_screened_out": "Likely screened out",
    "apply": "Apply",
    "stretch": "Stretch: apply if you can explain the gaps",
    "long_shot": "Long shot",
}
NAMED_LIMIT = 3  # most requirements that one reason names
YEARS_STRETCH_SHARE = 0.75  # this share of the asked years caps at Stretch; less, at Long shot
# Legal bans: the only knockouts whose absence in the CV means "Likely screened out".
HARD_KNOCKOUTS = frozenset({"work_authorization", "clearance", "certification_license"})
CODE_SENTENCE = "The job asks for"  # how the sentences code writes with levels or years begin
_BAND_RANK = {"long_shot": 0, "stretch": 1, "apply": 2}


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
    recency: dict[str, RecencyCheck] | None = None,
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
    counted = [
        r
        for r in job.requirements
        if r.importance == "required"
        and r.id not in excluded
        and (r.id not in flagged or r.id in included)
    ]

    risks = _counted_risks(job, hidden_risks or [])
    failed = [r for r in risks if _is_failed(r)]
    unanswered = [r for r in risks if _is_unanswered(r)]
    notes = [_note(r) for r in risks if _is_note(r)]

    # Minimum years the CV's own dates fall short of: a serious risk, never a screen-out.
    short = [r for r in counted if _years_short(assessments.get(r.id))]
    years_reasons = [
        VerdictReason(text=years_sentence(assessments[r.id].years_check), requirement_ids=[r.id])
        for r in short
    ]

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

    missing = [r for r in active if status(r.id) == "missing" and r not in short]
    # Hard: a legal ban the CV shows, or any knockout the candidate answered no to.
    hard = [
        r
        for r in missing
        if r.knockout_type in HARD_KNOCKOUTS or assessments[r.id].source == "user_answer"
    ]
    soft = [r for r in missing if r not in hard]  # a top risk that caps the band at Long shot
    top = years_reasons + [
        VerdictReason(text=_soft_reason(r, assessments[r.id], recency), requirement_ids=[r.id])
        for r in soft
    ]
    if hard or failed:
        return Verdict(
            label="likely_screened_out",
            title=TITLES["likely_screened_out"],
            # Nothing here suggests tailoring the CV: no edit fixes a screen-out.
            badges=[b for b in badges if b != "tailor_first"],
            reasons=_tidy(
                [
                    VerdictReason(
                        text=_would_reject(f'"{r.quote}"'),
                        requirement_ids=[r.id],
                    )
                    for r in hard
                ]
                + [
                    VerdictReason(
                        text=_would_reject(f'"{r.quote}"' if r.quote else "This hidden barrier"),
                        requirement_ids=list(r.requirement_ids),
                    )
                    for r in failed
                ]
                + top
                + notes
            ),
        )

    band, band_reasons = _band(job, assessments, score, excluded, flagged, included, config)
    band = "long_shot" if soft else _capped(band, [assessments[r.id] for r in short])
    # Unknown knockouts, and minimum-years requirements whose incomplete dates ask a question.
    unknown = [
        r
        for r in counted
        if status(r.id) == "unknown"
        and (r in active or (asks_min_years(r) and bool(assessments[r.id].question)))
    ]
    if unknown or unanswered:
        n = len(unknown) + len(unanswered)
        return Verdict(
            label="answer_questions",
            title=f"Answer {n} question{'s' if n != 1 else ''} first",
            badges=badges,
            reasons=_tidy(
                top
                + [
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
                + notes
            ),
            provisional=True,
        )

    return Verdict(
        label=band,
        title=TITLES[band],
        badges=badges,
        reasons=_tidy(top + band_reasons + notes),
    )


def _soft_reason(
    r: Requirement, assessment: RequirementAssessment, recency: dict[str, RecencyCheck] | None
) -> str:
    """Why a soft knockout counts against the candidate, with numbers when code has them: the
    recency check's sentence when the posting's window ruled it out, the code's own sentence
    (levels, years: "The job asks for English at C1; your CV states B2."), else the requirement
    in plain words."""
    check = (recency or {}).get(r.id)
    if check is not None and check.effect == "downgraded" and check.explanation:
        return check.explanation
    if assessment.rationale.startswith(CODE_SENTENCE):
        return assessment.rationale
    return f"{CODE_SENTENCE} {clean_prose(r.label)}; your CV does not show it."


def _years_short(assessment: RequirementAssessment | None) -> bool:
    """Missing because the CV's own, complete dates add up to less than the asked years."""
    check = assessment.years_check if assessment is not None else None
    return (
        check is not None
        and check.reliable
        and assessment.status == "missing"
        and assessment.source == "cv"
        and check.cv_months < check.min_years * 12
    )


def _capped(band: str, short: list[RequirementAssessment]) -> str:
    """A band no higher than each years shortfall allows: Stretch with at least 75% of the asked
    years, Long shot below that."""
    for assessment in short:
        share = assessment.years_check.share
        cap = "stretch" if share >= YEARS_STRETCH_SHARE else "long_shot"
        if _BAND_RANK[cap] < _BAND_RANK[band]:
            band = cap
    return band


def _tidy(reasons: list[VerdictReason]) -> list[VerdictReason]:
    """Every reason without raw IDs (the IDs stay in requirement_ids); empty ones are dropped."""
    tidy = []
    for reason in reasons:
        text = clean_prose(reason.text)
        if text:
            tidy.append(reason.model_copy(update={"text": text}))
    return tidy


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
    """One short sentence: the risk's explanation, or the posting's words when it has none."""
    said = short_sentence(r.explanation) or r.quote
    return VerdictReason(
        text=f"Hidden screening risk: {said}",
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
