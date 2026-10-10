"""Score and verdict, both computed in code from published weights."""

from typing import Literal

from pydantic import BaseModel, Field

VerdictLabel = Literal["likely_screened_out", "answer_questions", "apply", "stretch", "long_shot"]
Badge = Literal["tailor_first", "screening_risk", "posting_red_flags"]


class Contribution(BaseModel):
    requirement_id: str
    label: str
    category: str
    importance: str
    status: str
    weight: float
    credit: float
    points_won: float
    points_lost: float
    excluded_reason: str | None = None  # "not_relevant", "flagged_R1", "flagged_R2", "gate"


class ScoreBreakdown(BaseModel):
    fit: float | None  # None when nothing is scorable
    coverage: float | None
    coverage_numerator: float
    coverage_denominator: float
    pending_points: float  # Fit points waiting on unknown requirements
    contributions: list[Contribution] = Field(default_factory=list)
    summary: str = ""


class VerdictReason(BaseModel):
    text: str
    requirement_ids: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    label: VerdictLabel
    title: str
    badges: list[Badge] = Field(default_factory=list)
    reasons: list[VerdictReason] = Field(default_factory=list)
    provisional: bool = False
