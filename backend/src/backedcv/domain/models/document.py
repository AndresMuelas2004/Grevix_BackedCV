"""The rebuilt CV: ordered sections and items whose every line records where it came from."""

from typing import Literal

from pydantic import BaseModel, Field

from backedcv.domain.models.cv import SectionType

LineKind = Literal["text", "bullet"]


class DocLine(BaseModel):
    text: str
    origin: str  # an original line ID (L012) or an accepted suggestion ID (S03)
    kind: LineKind = "text"


class DocItem(BaseModel):
    """One block inside a section: a job, a degree, a project, or a group of loose lines."""

    id: str  # the CVEntry ID when the block is an entry, else "<section_id>-i<n>"
    lines: list[DocLine] = Field(default_factory=list)


class DocSection(BaseModel):
    id: str  # the CVSection ID, or "added-<type>" for a section created by a suggestion
    type: SectionType
    heading: str
    heading_origin: str | None = None  # the heading's line ID, None for a standard heading
    items: list[DocItem] = Field(default_factory=list)


class DocContact(BaseModel):
    name: str | None = None
    details: list[str] = Field(default_factory=list)  # email, phone, location, links
    origins: list[str] = Field(default_factory=list)  # line IDs the contact came from


class CVDocument(BaseModel):
    contact: DocContact = Field(default_factory=DocContact)
    sections: list[DocSection] = Field(default_factory=list)


class DiffLine(BaseModel):
    section_id: str
    status: Literal["unchanged", "changed", "added", "removed"]
    before: str | None = None
    after: str | None = None
    origin: str | None = None


class BuildReport(BaseModel):
    diff: list[DiffLine] = Field(default_factory=list)
    coverage_before: float | None = None
    coverage_after: float | None = None
    fit: float | None = None
    roundtrip_ok: bool | None = None
    roundtrip_issues: list[str] = Field(default_factory=list)
    built_by: Literal["agent", "fallback"] = "fallback"
    validation_errors: list[str] = Field(default_factory=list)
