"""How well the CV covers each requirement, always with receipts."""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["met", "partial", "missing", "unknown"]
MatchType = Literal["exact", "alias", "semantic", "inferred", "user_answer"]


class Evidence(BaseModel):
    ref: str  # an L or F ID
    quote: str  # filled by code from the CV, never by the model
    match_type: MatchType


class RequirementAssessment(BaseModel):
    requirement_id: str
    status: Status
    evidence: list[Evidence] = Field(default_factory=list)
    rationale: str = ""
    keyword_present: bool = False
    source: Literal["cv", "user_answer"] = "cv"
    question: str | None = None  # for unknown knockouts: what the employer is likely to ask


class CandidateFacts(BaseModel):
    """Optional answers that resolve knockout questions. They never enter the CV text."""

    work_authorization: list[str] | None = None  # countries
    needs_sponsorship: bool | None = None
    location: str | None = None
    willing_to_relocate: bool | None = None
    languages: list[str] | None = None
    licenses: list[str] | None = None
