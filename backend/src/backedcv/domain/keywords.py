"""Exact term matching that survives C++, C#, .NET, Node.js and light plural or tense changes."""

import re
from dataclasses import dataclass
from functools import lru_cache

from backedcv.domain.models import CVLine, Requirement
from backedcv.domain.text import fold_lower

_INFLECTIONS = r"(?:s|es|d|ed|ing)?"
_LEFT = r"(?<![a-z0-9])"
_RIGHT = r"(?![a-z0-9+#])"


def _fold_for_match(text: str) -> str:
    # Hyphens and slashes between words act as spaces: "machine-learning" = "machine learning".
    text = fold_lower(text)
    return re.sub(r"(?<=[a-z0-9])[-/](?=[a-z0-9])", " ", text)


@lru_cache(maxsize=4096)
def _pattern(term: str) -> re.Pattern[str] | None:
    folded = _fold_for_match(term)
    if not folded:
        return None
    escaped = re.escape(folded).replace(r"\ ", r"\s+")
    # Only plain words of 4+ letters get inflections, so "Go" never matches "Goes".
    suffix = _INFLECTIONS if re.fullmatch(r"[a-z][a-z ]{3,}", folded) else ""
    return re.compile(_LEFT + escaped + suffix + _RIGHT)


def contains_term(text: str, term: str) -> bool:
    pattern = _pattern(term)
    return bool(pattern and pattern.search(_fold_for_match(text)))


def count_term(text: str, term: str) -> int:
    pattern = _pattern(term)
    return len(pattern.findall(_fold_for_match(text))) if pattern else 0


@dataclass(frozen=True)
class KeywordHit:
    line_id: str
    term: str
    match_type: str  # "exact" (a posting term) or "alias"


def keyword_hits(requirement: Requirement, lines: list[CVLine]) -> list[KeywordHit]:
    """Lines where a posting term (exact) or one of its aliases (alias) appears literally."""
    hits: list[KeywordHit] = []
    seen: set[tuple[str, str]] = set()
    candidates = [(t, "exact") for t in requirement.terms] + [
        (a, "alias") for a in requirement.aliases
    ]
    for term, kind in candidates:
        for line in lines:
            key = (line.id, kind)
            if key in seen:
                continue
            if contains_term(line.text, term):
                seen.add(key)
                hits.append(KeywordHit(line.id, term, kind))
    return hits


def keyword_present(requirement: Requirement, lines: list[CVLine]) -> bool:
    """True when a posting term or alias appears literally anywhere in the CV."""
    full_text = "\n".join(line.text for line in lines)
    return any(contains_term(full_text, t) for t in [*requirement.terms, *requirement.aliases])
