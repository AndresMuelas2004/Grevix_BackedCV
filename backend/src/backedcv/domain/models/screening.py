"""Hidden screening risks, recency of evidence and the corroboration gate.

A requirement can look met (the keyword is in the CV) and still be silently rejected: the only
evidence is old and the posting asks for recent experience, or a buried sentence rules the
candidate out. These models carry those findings with the posting's own words.
"""

import re
from collections.abc import Mapping
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


# Sentences shown to the user never carry raw IDs (requirements R.., barriers H.., CV lines L..,
# facts F..): the IDs live in their own fields (requirement_ids, refs).

MAX_WORDS = 20  # one sentence of about this many words; a few more are kept whole
_SLACK_WORDS = 5
_CITATION = r"(?:L\d{3,4}|F\d{2})"  # CV lines and computed facts: the frontend shows them as tags
_OTHER_ID = r"(?:R\d{2,3}|HC\d{1,2}|H\d{2})"
_ANY_ID = rf"(?:{_OTHER_ID}|{_CITATION})"
_LEAD = r"(?:(?i:see|cf\.?|ids?|requirements?|lines?|barriers?|risks?|facts?)\s+)?"


def _id_group(ids: str) -> re.Pattern[str]:
    """A bracketed list of IDs, such as "(R17)" or "[R02, R05]", with the space before it."""
    return re.compile(rf"\s*[(\[]\s*{_LEAD}{ids}(?:\s*(?:,|/|&|(?i:and|or))\s*{ids})*\s*[)\]]")


_GROUPS = {True: _id_group(_OTHER_ID), False: _id_group(_ANY_ID)}
_BARE = {True: re.compile(rf"\b{_OTHER_ID}\b"), False: re.compile(rf"\b{_ANY_ID}\b")}
_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]")
_SPACE_RUN = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_ENDINGS = ".!?…"
_CLOSERS = "\"')]”’"


def clean_prose(
    text: str | None, labels: Mapping[str, str] | None = None, *, keep_citations: bool = False
) -> str:
    """The text without raw IDs. A bracketed list of IDs goes away; a bare requirement ID becomes
    its label when `labels` knows it, and any other bare ID goes away. With `keep_citations`, CV
    line and fact IDs (L012, F01) stay: the frontend turns them into citation tags."""
    value = _GROUPS[keep_citations].sub("", text or "")
    value = _BARE[keep_citations].sub(lambda m: (labels or {}).get(m.group(0), ""), value)
    value = _EMPTY_BRACKETS.sub("", value)
    value = _SPACE_RUN.sub(" ", value)
    return _SPACE_BEFORE_PUNCT.sub(r"\1", value).strip()


def short_sentence(text: str | None, max_words: int = MAX_WORDS) -> str:
    """The first sentence of a clean text, cut to `max_words` words when it runs much longer
    (an ellipsis marks the cut)."""
    value = clean_prose(text)
    first = _SENTENCE_BREAK.split(value, maxsplit=1)[0].strip()
    words = first.split()
    if len(words) <= max_words + _SLACK_WORDS:
        return first
    return " ".join(words[:max_words]).rstrip(",;:-") + "…"


def join_sentences(*parts: str | None) -> str:
    """Sentences joined by one space, each ending with a full stop (added when it has none)."""
    sentences: list[str] = []
    for part in parts:
        sentence = (part or "").strip()
        if not sentence:
            continue
        if sentence.rstrip(_CLOSERS)[-1:] not in _ENDINGS:
            sentence += "."
        sentences.append(sentence)
    return " ".join(sentences)
