"""LLM-facing output schemas (OpenAI strict mode).

Rules for strict mode: every field required, optional values nullable, no dict fields.
Field descriptions carry per-field instructions; they reach the model through the schema.
Domain models are built from these drafts in code, never trusted as-is.
"""

from typing import Literal

from pydantic import BaseModel, Field

SectionKind = Literal[
    "contact",
    "summary",
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "languages",
    "other",
]
CategoryKind = Literal[
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
KnockoutKind = Literal[
    "work_authorization",
    "location",
    "language",
    "certification_license",
    "experience_years",
    "education",
    "clearance",
    "availability",
]


# 1. CV structure ---------------------------------------------------------------------


class SectionDraft(BaseModel):
    type: SectionKind
    heading_line_id: str | None = Field(
        description="ID of the heading line (e.g. 'L007'), or null if the section has none."
    )
    first_line_id: str = Field(description="First line ID of the section, heading included.")
    last_line_id: str = Field(description="Last line ID of the section.")


class EntryDraft(BaseModel):
    kind: Literal["job", "education", "project"]
    title: str | None = Field(description="Job title, degree or project name, copied verbatim.")
    organization: str | None = Field(description="Employer or school, copied verbatim.")
    location: str | None = Field(description="Location as written, or null.")
    first_line_id: str
    last_line_id: str
    date_line_id: str | None = Field(description="ID of the line that holds the dates, or null.")


class CVStructureDraft(BaseModel):
    name_line_id: str | None = Field(description="Line with the candidate's name, or null.")
    location_line_id: str | None = Field(
        description="Line with the candidate's own location, or null."
    )
    sections: list[SectionDraft]
    entries: list[EntryDraft]


# 2. Job posting --------------------------------------------------------------------------


class RequirementDraft(BaseModel):
    quote: str = Field(
        description="The exact sentence or bullet of the posting this requirement comes from, "
        "copied verbatim."
    )
    terms: list[str] = Field(
        description="1 to 3 short spans copied verbatim from the quote that a recruiter would "
        "search for (e.g. 'AWS', 'Kubernetes', 'Bachelor's degree'). Empty for soft wording."
    )
    label: str = Field(description="Short display label, at most 6 words.")
    category: CategoryKind
    importance: Literal["required", "preferred"]
    cue: str | None = Field(
        description="Words in the posting that signal the importance ('must', 'nice to have'), "
        "or null when importance is inferred from the section."
    )
    knockout_type: KnockoutKind | None = Field(
        description="Set only when this requirement is the kind employers ask as a yes/no "
        "screening question. Null otherwise."
    )
    min_years: float | None = Field(description="Minimum years asked, or null.")
    aliases: list[str] = Field(
        description="Common abbreviations or expansions of the terms ('JS' for 'JavaScript'). "
        "At most 3. Empty if none."
    )


class JobExtractionDraft(BaseModel):
    title: str | None
    company: str | None
    seniority: str | None = Field(description="e.g. 'entry level', 'senior', or null.")
    seniority_quote: str | None = Field(description="Verbatim words that state the seniority.")
    location: str | None
    remote_policy: str | None = Field(description="'onsite', 'hybrid', 'remote' or null.")
    employment_type: str | None
    salary_present: bool
    requirements: list[RequirementDraft]


# 3. Matching ------------------------------------------------------------------------------


class AssessmentDraft(BaseModel):
    requirement_id: str
    status: Literal["met", "partial", "missing", "unknown"]
    line_ids: list[str] = Field(
        description="IDs of the CV lines or computed facts (L... or F...) that prove the status. "
        "Empty when missing or unknown."
    )
    match_type: Literal["exact", "alias", "semantic", "inferred"] | None
    rationale: str = Field(
        description="One short plain sentence, at most 20 words, no jargon and no IDs. "
        "Explain semantic matches."
    )


class MatchChunkDraft(BaseModel):
    assessments: list[AssessmentDraft]
