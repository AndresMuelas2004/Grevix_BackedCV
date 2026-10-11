"""The job posting broken into requirements."""

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "hard_skill",
    "soft_skill",
    "experience_years",
    "job_title",
    "education",
    "certification_license",
    "language",
    "work_authorization",
    "location",
    "clearance",
    "availability",
    "other",
]
Importance = Literal["required", "preferred"]
KnockoutType = Literal[
    "work_authorization",
    "location",
    "language",
    "certification_license",
    "experience_years",
    "education",
    "clearance",
    "availability",
]


class Requirement(BaseModel):
    id: str  # R01, R02, ...
    label: str
    quote: str
    quote_located: bool = True
    terms: list[str] = Field(default_factory=list)
    category: Category
    importance: Importance
    cue: str | None = None
    knockout_type: KnockoutType | None = None
    min_years: float | None = None
    aliases: list[str] = Field(default_factory=list)
    # The posting bullet or sentence the quote sits in ("U07": the 7th), set in code from the
    # posting text. Requirements that share a unit share its weight in the score; None (older
    # states) means the requirement is a unit of its own.
    source_unit: str | None = None


class JobPosting(BaseModel):
    title: str | None = None
    company: str | None = None
    seniority: str | None = None
    seniority_quote: str | None = None
    location: str | None = None
    remote_policy: str | None = None
    employment_type: str | None = None
    salary_present: bool = False
    requirements: list[Requirement] = Field(default_factory=list)


class RequirementFlag(BaseModel):
    """R1/R2: absurd requirements that leave Fit unless the user includes them."""

    rule_id: Literal["R1", "R2"]
    requirement_ids: list[str]
    severity: Literal["info", "warning"] = "warning"
    explanation: str


class PostingBanner(BaseModel):
    """R3/R4: posting-level warnings that never touch the score."""

    rule_id: Literal["R3", "R4"]
    requirement_ids: list[str] = Field(default_factory=list)
    severity: Literal["info", "warning"] = "info"
    explanation: str
