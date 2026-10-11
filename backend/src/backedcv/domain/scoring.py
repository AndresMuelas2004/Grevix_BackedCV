"""Fit and Keyword coverage from published weights. Every point traces to one requirement, and
the requirements of one posting bullet share its weight (see `unit_weights`)."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from backedcv.config import load
from backedcv.domain.models import (
    Contribution,
    Requirement,
    RequirementAssessment,
    ScoreBreakdown,
)


@dataclass(frozen=True)
class ScoringConfig:
    category_weights: dict[str, float]
    importance_multipliers: dict[str, float]
    credit: dict[str, float]
    coverage_categories: frozenset[str]
    apply_min_fit: float
    stretch_min_fit: float
    tailor_first_gap: float
    blocking_min_category_weight: float
    r1_min_years: float
    r1_seniority_words: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def default(cls) -> "ScoringConfig":
        raw = load("scoring")
        return cls(
            category_weights=raw["category_weights"],
            importance_multipliers=raw["importance_multipliers"],
            credit=raw["credit"],
            coverage_categories=frozenset(raw["coverage_categories"]),
            apply_min_fit=raw["verdict"]["apply_min_fit"],
            stretch_min_fit=raw["verdict"]["stretch_min_fit"],
            tailor_first_gap=raw["verdict"]["tailor_first_gap"],
            blocking_min_category_weight=raw["verdict"]["blocking_min_category_weight"],
            r1_min_years=raw["rules"]["r1_min_years"],
            r1_seniority_words=tuple(raw["rules"]["r1_seniority_words"]),
        )

    def weight(self, requirement: Requirement) -> float:
        return (
            self.category_weights.get(requirement.category, 1)
            * self.importance_multipliers[requirement.importance]
        )

    def is_gate(self, requirement: Requirement) -> bool:
        return self.category_weights.get(requirement.category, 1) == 0


def exclusion_reason(
    requirement: Requirement,
    config: ScoringConfig,
    excluded_ids: Iterable[str],
    flagged: dict[str, str],
    included_flagged_ids: Iterable[str],
) -> str | None:
    """Why a requirement leaves the score, or None if it counts."""
    if requirement.id in set(excluded_ids):
        return "not_relevant"
    if requirement.id in flagged and requirement.id not in set(included_flagged_ids):
        return f"flagged_{flagged[requirement.id]}"
    if config.is_gate(requirement):
        return "gate"
    return None


def unit_weights(counted: list[Requirement], config: ScoringConfig) -> dict[str, float]:
    """The weight of each counted requirement. A posting unit (one bullet or sentence) weighs as
    its heaviest counted requirement, and the counted requirements that come from it share that
    weight equally, so splitting one bullet into several requirements cannot move the score.
    A requirement with no unit is a unit of its own."""
    units: dict[str, list[Requirement]] = {}
    for req in counted:
        units.setdefault(req.source_unit or f"own:{req.id}", []).append(req)
    weights: dict[str, float] = {}
    for members in units.values():
        share = max(config.weight(req) for req in members) / len(members)
        weights.update({req.id: share for req in members})
    return weights


def compute_score(
    requirements: list[Requirement],
    assessments: dict[str, RequirementAssessment],
    *,
    excluded_ids: Iterable[str] = (),
    flagged: dict[str, str] | None = None,
    included_flagged_ids: Iterable[str] = (),
    config: ScoringConfig | None = None,
) -> ScoreBreakdown:
    config = config or ScoringConfig.default()
    flagged = flagged or {}
    excluded_ids, included_flagged_ids = set(excluded_ids), set(included_flagged_ids)
    reasons = {
        req.id: exclusion_reason(req, config, excluded_ids, flagged, included_flagged_ids)
        for req in requirements
    }
    weights = unit_weights([r for r in requirements if reasons[r.id] is None], config)

    rows: list[tuple[Requirement, RequirementAssessment | None, float, float, str | None]] = []
    fit_den = cov_num = cov_den = 0.0
    for req in requirements:
        assessment = assessments.get(req.id)
        status = assessment.status if assessment else "unknown"
        reason = reasons[req.id]
        w = weights.get(req.id, config.weight(req))  # an excluded row shows its own weight
        credit = config.credit[status]
        rows.append((req, assessment, w, credit, reason))
        if reason is None:
            fit_den += w
            if req.category in config.coverage_categories:
                cov_den += w
                if assessment and assessment.keyword_present:
                    cov_num += w

    fit_num = sum(w * c for _, _, w, c, reason in rows if reason is None)
    contributions: list[Contribution] = []
    pending = 0.0
    for req, assessment, w, credit, reason in rows:
        status = assessment.status if assessment else "unknown"
        share = 100 * w / fit_den if reason is None and fit_den else 0.0
        if reason is None and status == "unknown":
            pending += share
        contributions.append(
            Contribution(
                requirement_id=req.id,
                label=req.label,
                category=req.category,
                importance=req.importance,
                status=status,
                weight=w,
                credit=credit,
                points_won=round(share * credit, 1),
                points_lost=round(share * (1 - credit), 1),
                excluded_reason=reason,
            )
        )

    fit = round(100 * fit_num / fit_den, 1) if fit_den else None
    coverage = round(100 * cov_num / cov_den, 1) if cov_den else None
    breakdown = ScoreBreakdown(
        fit=fit,
        coverage=coverage,
        coverage_numerator=cov_num,
        coverage_denominator=cov_den,
        pending_points=round(pending, 1),
        contributions=contributions,
    )
    breakdown.summary = summarize(breakdown)
    return breakdown


def round_half_up(value: float) -> int:
    """Whole number for a sentence. Halves go up (51.5 -> 52), unlike Python's round()."""
    return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def summarize(score: ScoreBreakdown) -> str:
    """One sentence that explains the Fit score: requirements met and the biggest losses."""
    if score.fit is None:
        return "No scorable requirements were found in this posting."
    counted = [c for c in score.contributions if c.excluded_reason is None]
    required = [c for c in counted if c.importance == "required"]
    met = sum(1 for c in required if c.status == "met")
    # A loss that rounds to 0 would read "-0", so it is not named.
    losses = sorted(
        (c for c in counted if round_half_up(c.points_lost) > 0),
        key=lambda c: -c.points_lost,
    )[:3]
    parts = [f"Fit {round_half_up(score.fit)}: you meet {met} of {len(required)} required items"]
    if losses:
        described = []
        for c in losses:
            note = {"partial": "partial, ", "unknown": "unconfirmed, "}.get(c.status, "")
            described.append(f"{c.label} ({note}-{round_half_up(c.points_lost)})")
        parts.append("biggest losses: " + ", ".join(described))
    return "; ".join(parts) + "."
