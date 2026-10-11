"""The CV as read by the app: numbered lines plus structure that only points at line IDs."""

from typing import Literal

from pydantic import BaseModel, Field

from backedcv.domain.redaction import numbered_rows

LineSource = Literal["body", "header", "footer", "textbox", "table"]
SectionType = Literal[
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
EntryKind = Literal["job", "education", "project"]


class CVLine(BaseModel):
    id: str  # L001, L002, ...
    text: str
    page: int = 1
    source: LineSource = "body"
    bold: bool = False
    size: float | None = None


class ComputedFact(BaseModel):
    """A number computed by code that suggestions and the verifier may cite (F01, F02, ...)."""

    id: str
    text: str
    derived_from: list[str] = Field(default_factory=list)


class CVSection(BaseModel):
    id: str
    heading_line_id: str | None
    type: SectionType
    line_ids: list[str]


class CVEntry(BaseModel):
    id: str
    section_id: str
    kind: EntryKind
    title: str | None = None
    organization: str | None = None
    location: str | None = None
    start: str | None = None  # YYYY-MM, or YYYY when the CV gives only the year
    end: str | None = None  # YYYY-MM, YYYY or "present"; None for a single date
    date_source: Literal["parser", "model", "none"] = "none"
    line_ids: list[str] = Field(default_factory=list)
    month_unknown: bool = False  # the start or the end shows only the year: no month is invented
    # Jobs with a start and an end (or "present") only: the months this entry adds, counted
    # inclusively and at the shortest when a date shows only the year. None: not counted.
    months_counted: int | None = None


class ContactField(BaseModel):
    value: str
    line_id: str


class Contact(BaseModel):
    name: ContactField | None = None
    email: ContactField | None = None
    phone: ContactField | None = None
    location: ContactField | None = None
    links: list[ContactField] = Field(default_factory=list)


class ParseWarning(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    line_ids: list[str] = Field(default_factory=list)


class ParsedCV(BaseModel):
    lines: list[CVLine]
    facts: list[ComputedFact] = Field(default_factory=list)
    sections: list[CVSection] = Field(default_factory=list)
    entries: list[CVEntry] = Field(default_factory=list)
    contact: Contact = Field(default_factory=Contact)
    total_years: float | None = None
    total_months: int | None = None  # the months behind total_years: job periods, overlaps once
    # True when a job date shows only the year or a job has no dates: the real total may be longer.
    total_is_minimum: bool = False
    dates_note: str | None = None  # one plain sentence saying why the total is a minimum

    def texts_by_ref(self) -> dict[str, str]:
        """Every citable reference (L and F IDs) mapped to its text."""
        refs = {line.id: line.text for line in self.lines}
        refs.update({fact.id: fact.text for fact in self.facts})
        return refs

    def numbered(self, include_facts: bool = True) -> str:
        """The CV in the only format the model sees: `L012 | text`, then the computed facts.
        Contact details are replaced by placeholders (domain/redaction.py)."""
        rows = [(line.id, line.text) for line in self.lines]
        if include_facts:
            rows += [(fact.id, fact.text) for fact in self.facts]
        return numbered_rows(rows)
