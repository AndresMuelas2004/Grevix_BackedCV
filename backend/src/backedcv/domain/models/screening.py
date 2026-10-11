"""Challenge Card 1: hidden screening risks, recency of evidence and the corroboration gate.

A requirement can look met (the keyword is in the CV) and still be silently rejected: the only
evidence is old and the posting asks for recent experience, or a buried sentence rules the
candidate out. These models carry those findings, always with the posting's own words.
"""

from typing import Literal

from pydantic import BaseModel, Field

RecencyBand = Literal["recent", "aging", "stale", "undated"]
RiskLevel = Literal["high", "medium", "low"]
BarrierKind = Literal[
    "work_authorization",  # work permit, no visa sponsorship, citizenship
    "location",  # residency, on-site days, relocation, time zone
    "recency",  # a multi-year recency rule ("within the last 5 years")
    "graduation_window",  # graduated in or after a year, "recent graduates only"
    "language",  # a language level
    "clearance",  # security clearance, background check
    "availability",  # start date, shifts, travel, on-call
    "other",
]
# Barriers that rewording a CV can never fix: the candidate answers them instead.
ELIGIBILITY_KINDS: frozenset[str] = frozenset(
    {"work_authorization", "location", "graduation_window", "language", "clearance", "availability"}
)
GateName = Literal["backed", "recent_enough", "not_blocked"]


class RecencyRule(BaseModel):
    """An explicit recency rule stated in the posting ("within the last 5 years")."""

    quote: str  # verbatim from the posting, located by code
    window_years: float
    requirement_ids: list[str] = Field(default_factory=list)  # empty: a general rule
    source: Literal["rule", "model"] = "rule"  # found by a code pattern or by the model


class RecencyCheck(BaseModel):
    """When the CV last shows a requirement, from the dates of the entries its evidence is in."""

    requirement_id: str
    original_status: str  # the status before the recency check
    last_used: str | None = None  # YYYY-MM of the most recent dated evidence line
    years_since: float | None = None
    band: RecencyBand = "undated"
    evidence_refs: list[str] = Field(default_factory=list)  # the L lines considered
    rule: RecencyRule | None = None  # the strictest explicit rule that applies, if any
    within_rule: bool | None = None  # None when no rule applies
    effect: Literal["none", "warning", "downgraded"] = "none"
    explanation: str = ""


class BarrierItem(BaseModel):
    """A buried or ambiguous disqualifier found in the posting, with its exact words."""

    id: str  # H01, H02, ...
    kind: BarrierKind
    quote: str  # verbatim from the posting, located by code
    explicit: bool = True  # stated plainly (True) or only implied (False)
    place: str | None = None  # the country, region or city it names, if any
    window_years: float | None = None  # recency barriers only
    requirement_ids: list[str] = Field(default_factory=list)  # requirements it affects
    explanation: str = ""  # why a screener may silently reject
    action: str = ""  # what the candidate can do
    question: str | None = None  # a yes/no question that resolves it
    source: Literal["model", "rule"] = "model"


class HiddenRisk(BaseModel):
    """A barrier checked against the CV and the candidate's answers, or a composite of several."""

    id: str  # the barrier's H ID; composites are HC1, HC2, ...
    kind: BarrierKind | Literal["composite"]
    quote: str = ""  # empty for a composite
    explanation: str
    action: str = ""
    risk: RiskLevel
    requirement_ids: list[str] = Field(default_factory=list)
    question: str | None = None  # answered through facts.answers[id]
    resolved: bool = False  # the candidate answered yes
    confirmed: bool = False  # the candidate answered no
    component_ids: list[str] = Field(default_factory=list)  # composites: the risks combined
    cv_refs: list[str] = Field(default_factory=list)  # CV lines that show the conflict


class ScreeningFlag(BaseModel):
    """A requirement that looks met but carries a high chance of silent rejection."""

    requirement_id: str
    risk: RiskLevel
    reasons: list[str] = Field(default_factory=list)  # plain sentences
    risk_ids: list[str] = Field(default_factory=list)  # the H IDs behind it


class GatePass(BaseModel):
    """One pass of the corroboration gate. `hard` failures refuse the edit as not viable."""

    name: GateName
    ok: bool
    hard: bool = True
    detail: str | None = None


class Refusal(BaseModel):
    """An edit refused as not viable: before generation (a requirement) or after (a suggestion)."""

    requirement_id: str
    gate: Literal["recent_enough", "not_blocked"]
    reason: str
    refs: list[str] = Field(default_factory=list)  # the old or conflicting evidence lines
    suggestion_id: str | None = None  # set when a generated suggestion was refused
