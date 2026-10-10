"""Text folding shared by quote checks and keyword matching."""

import difflib
import re
import unicodedata

_TRANSLATE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        " ": " ",
        " ": " ",
        " ": " ",
        "­": "",
        "​": "",
        "•": " ",
    }
)
_SPACES = re.compile(r"\s+")


def fold(text: str) -> str:
    """NFKC, straight quotes, plain dashes, regular spaces, collapsed whitespace. Case kept."""
    text = unicodedata.normalize("NFKC", text).translate(_TRANSLATE)
    return _SPACES.sub(" ", text).strip()


def fold_lower(text: str) -> str:
    return fold(text).casefold()


def locate_quote(quote: str, source: str) -> str | None:
    """Return the verbatim span of `source` that matches `quote`, or None.

    Tries an exact folded match first, then a difflib alignment that tolerates
    small differences (the model dropping a bullet, changing a quote mark).
    """
    q = fold_lower(quote)
    if not q:
        return None
    s_folded = fold_lower(source)
    if q in s_folded:
        return _span_from_folded(source, q)

    matcher = difflib.SequenceMatcher(None, s_folded, q, autojunk=False)
    match = matcher.find_longest_match(0, len(s_folded), 0, len(q))
    if match.size == 0:
        return None
    start = max(0, match.a - match.b)
    window = s_folded[start : start + len(q) + 10]
    ratio = difflib.SequenceMatcher(None, window[: len(q)], q, autojunk=False).ratio()
    if ratio < 0.85:
        return None
    return _span_from_folded(source, window[: len(q)])


def _span_from_folded(source: str, folded_span: str) -> str:
    """Map a span found in the folded source back to readable text (folded, original case)."""
    folded = fold(source)
    idx = folded.casefold().find(folded_span)
    if idx < 0:
        return folded_span
    return folded[idx : idx + len(folded_span)]
