"""Deterministic clean-up of the extracted requirements, so the model's run-to-run variance cannot
change them. Each requirement is tied to the posting unit its quote sits in, importance follows the
posting's own wording and headings, duplicates are merged, and order and IDs follow the posting.
Pure: no I/O."""

import re
from dataclasses import dataclass

from backedcv.domain.models import JobPosting, Requirement
from backedcv.domain.text import fold, fold_lower, locate_quote

RANK = {"preferred": 0, "required": 1}
# A skill and the years asked of it can be the same requirement; any other category only
# matches itself.
FAMILY = {"experience_years": "hard_skill"}
_FAR = 10**9  # position of a requirement whose quote is not in the posting: after the rest

_PREFERRED = (
    r"nice[- ]to[- ]haves?|preferred|bonus(?: points)?|pluses|a plus|plus|desirable|desired"
    r"|good[- ]to[- ]haves?|extra points|valorables?|se valorar[aá]|deseables?|valoramos"
)
_REQUIRED = (
    r"requirements?|required|must[- ]haves?|qualifications"
    r"|(?:minimum|basic|key|essential|core) (?:qualifications|requirements|skills)"
    r"|what (?:you|we)(?: will|'ll)? (?:need|bring)|what we(?: are|'re) looking for"
    r"|who you are|about you|you have|requisitos|imprescindibles?"
)
_OTHER = (
    r"about(?: [a-z]+){0,3}|(?:the|your) role|role|(?:key |your )?responsibilities|duties"
    r"|what (?:you|you'll|you will) (?:do|be doing)|what we offer|we offer|benefits|perks"
    r"|compensation|salary|how to apply|who we are|(?:our|the) team|location|job description"
    r"|overview|summary|funciones|responsabilidades|ofrecemos|beneficios|sobre nosotros"
)
_HEADINGS = (
    ("preferred", re.compile(rf"^(?:{_PREFERRED})\b")),
    ("required", re.compile(rf"^(?:{_REQUIRED})\b")),
    (None, re.compile(rf"^(?:{_OTHER})\b")),
)
_PREFERRED_CUE = re.compile(
    r"\bnice[- ]to[- ]have\b|\ba plus\b|\bpluses\b|\bbonus\b|\bpreferred\b|\bpreferably\b"
    r"|\bdesirable\b|\bideally\b|\badvantage(?:ous)?\b|\bgood[- ]to[- ]have\b|\bvalorables?\b"
    r"|\bse valorar[aá]\b|\bdeseables?\b"
)
_REQUIRED_CUE = re.compile(
    r"\bmust\b|\brequir(?:e|es|ed)\b|\bneeds? to\b|\bmandatory\b|\bessential\b"
    r"|\bimprescindibles?\b|\bobligatori[oa]s?\b|\brequerid[oa]s?\b|\bse requiere\b"
)
# A short line after a blank line that no pattern knows ("Good to know") still starts a new
# section: what follows keeps the model's importance instead of the previous section's.
_UNKNOWN_HEADING = re.compile(r"^[^.!?,;]{1,40}$")
_UNKNOWN_HEADING_WORDS = 5
# A bullet or numbered item, checked on the line as written (folding turns "•" into a space).
_BULLET = re.compile(r"^\s*(?:[•▪●◦‣·]|[-*–—>]\s|\d{1,2}[.)]\s)")
_DECORATION = "#*_ "
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[^\sa-zà-ÿ])")
_WORD = re.compile(r"[^\w+#]+")


@dataclass(frozen=True)
class Unit:
    """One bullet or sentence of the posting, with offsets in the folded posting."""

    id: str
    start: int
    end: int
    text: str  # folded, lowercase
    section: str | None  # "required" or "preferred" from the heading above it, or None
    heading: str | None  # that heading as written, used as the cue when it sets importance


def posting_units(posting: str) -> tuple[str, list[Unit]]:
    """The folded lowercase posting (lines joined by a space) and its units in order: each line
    split into sentences, each tagged with the section it sits in."""
    pieces: list[str] = []
    units: list[Unit] = []
    offset = 0
    section: str | None = None
    heading: str | None = None
    after_blank = True
    for line in posting.split("\n"):
        found = _heading(line)
        if found is not None:
            section, heading = found
        elif after_blank and _unknown_heading(line):
            section, heading = None, None
        after_blank = not line.strip()
        for sentence in _SENTENCE_END.split(fold(line)):
            text = fold_lower(sentence)
            if not text:
                continue
            if pieces:
                offset += 1  # the joining space
            units.append(
                Unit(f"U{len(units) + 1:02d}", offset, offset + len(text), text, section, heading)
            )
            pieces.append(text)
            offset += len(text)
    return " ".join(pieces), units


def _heading(line: str) -> tuple[str | None, str] | None:
    """(section, heading text) when the line is a section heading, or a line that starts with
    one and a colon ("Nice to have: dbt"); None for any other line."""
    if _BULLET.match(line):
        return None
    shown = fold(line).strip(_DECORATION)
    text = shown.casefold()
    if not text:
        return None
    for section, pattern in _HEADINGS:
        match = pattern.match(text)
        if match is None:
            continue
        rest = text[match.end() :]
        label = shown[: match.end()].strip(" :")
        if rest.startswith(":") or re.match(r"\s*\([^)]*\)\s*:?\s*$", rest):
            return section, label  # "Requirements:", "Nice to have: dbt", "Plus (optional)"
        rest = rest.strip(" :-*")
        if len(text) <= 60 and not text.endswith(".") and len(rest.split()) <= 3:
            return section, label
        return None
    return None


def _unknown_heading(line: str) -> bool:
    text = fold(line).strip(_DECORATION)
    return (
        not _BULLET.match(line)
        and _UNKNOWN_HEADING.match(text) is not None
        and len(text.split()) <= _UNKNOWN_HEADING_WORDS
    )


def _unit_at(units: list[Unit], position: int) -> Unit | None:
    for unit in units:
        if unit.start <= position < unit.end:
            return unit
    return None


def _position(req: Requirement, posting: str, folded: str) -> int | None:
    """Where the requirement's quote starts in the folded posting, or None if it is not there."""
    quote = fold_lower(req.quote)
    if quote and (at := folded.find(quote)) >= 0:
        return at
    located = locate_quote(req.quote, posting)
    if located and (at := folded.find(fold_lower(located))) >= 0:
        return at
    return None


def _term_offset(req: Requirement) -> int:
    """Where the first of the requirement's terms appears in its quote: orders the items of
    one bullet ("Python and SQL") the way the posting writes them."""
    quote = fold_lower(req.quote)
    found = [quote.find(fold_lower(t)) for t in req.terms]
    return min((at for at in found if at >= 0), default=0)


def _key(text: str) -> str:
    return " ".join(_WORD.sub(" ", fold_lower(text)).split())


def _terms_key(req: Requirement) -> frozenset[str]:
    return frozenset(key for key in (_key(t) for t in req.terms) if key)


def _same(a: Requirement, b: Requirement) -> bool:
    """The same requirement twice: one family of categories, and the same label or terms."""
    if FAMILY.get(a.category, a.category) != FAMILY.get(b.category, b.category):
        return False
    label, terms = _key(a.label), _terms_key(a)
    return (bool(label) and label == _key(b.label)) or (bool(terms) and terms == _terms_key(b))


def _union(*lists: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for item in (i for items in lists for i in items):
        seen.setdefault(_key(item), item)
    return list(seen.values())[:3]


def _merge(group: list[tuple[int, Requirement]]) -> tuple[int, Requirement]:
    """One requirement from duplicates: the primary one (most years asked, then required, then
    first in the posting) keeps its wording; importance and years are the strictest asked."""
    ordered = sorted(
        group,
        key=lambda item: (-(item[1].min_years or 0), -RANK[item[1].importance], item[0]),
    )
    position, primary = ordered[0]
    reqs = [req for _, req in ordered]
    years = [r.min_years for r in reqs if r.min_years is not None]
    importance = max((r.importance for r in reqs), key=RANK.__getitem__)
    merged = primary.model_copy(
        update={
            "importance": importance,
            "min_years": max(years) if years else None,
            "knockout_type": next((r.knockout_type for r in reqs if r.knockout_type), None),
            "terms": _union(*(r.terms for r in reqs)),
            "aliases": _union(*(r.aliases for r in reqs)),
            "cue": next((r.cue for r in reqs if r.importance == importance), primary.cue),
        }
    )
    return position, merged


def _importance(req: Requirement, unit: Unit | None) -> Requirement:
    """The posting's own words decide importance when they are clear: a cue in the bullet
    ("a plus", "must") first, then the section heading. Mixed cues leave the model's choice."""
    if unit is None:
        return req
    preferred = _PREFERRED_CUE.search(unit.text) is not None
    required = _REQUIRED_CUE.search(unit.text) is not None
    if preferred and required:
        return req
    if preferred or required:
        wanted, cue = ("preferred" if preferred else "required"), req.cue
    elif unit.section is not None:
        wanted, cue = unit.section, unit.heading
    else:
        return req
    if wanted == req.importance:
        return req
    return req.model_copy(update={"importance": wanted, "cue": cue})


def canonical_requirements(job: JobPosting, posting: str) -> JobPosting:
    """The job with its requirements tied to posting units, duplicates merged, sorted by position
    in the posting and renumbered R01, R02..."""
    folded, units = posting_units(posting)
    placed: list[tuple[int, int, Requirement]] = []
    for index, req in enumerate(job.requirements):
        start = _position(req, posting, folded)
        unit = _unit_at(units, start) if start is not None else None
        req = _importance(req, unit).model_copy(update={"source_unit": unit.id if unit else None})
        position = _FAR if start is None else start + _term_offset(req)
        placed.append((position, index, req))
    placed.sort(key=lambda item: (item[0], _key(item[2].label), item[1]))

    groups: list[list[tuple[int, Requirement]]] = []
    for position, _, req in placed:
        group = next((g for g in groups if _same(g[0][1], req)), None)
        if group is None:
            groups.append([(position, req)])
        else:
            group.append((position, req))
    merged = sorted((_merge(group) for group in groups), key=lambda item: item[0])
    requirements = [
        req.model_copy(update={"id": f"R{i:02d}"}) for i, (_, req) in enumerate(merged, start=1)
    ]
    return job.model_copy(update={"requirements": requirements})
