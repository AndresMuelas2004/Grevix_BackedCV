"""Text folding shared by quote checks and keyword matching, and the canonical form every CV and
posting takes when it enters the app (`normalize_text`)."""

import difflib
import re
import unicodedata

# Unicode format characters (category Cf, Unicode 15): invisible, they never change the words.
# Soft hyphen, zero-width space and joiners, direction marks, word joiner, BOM, tag characters...
_INVISIBLE = re.compile(
    "[\xad\U00000600-\U00000605\U0000061c\U000006dd\U0000070f\U00000890\U00000891"
    "\U000008e2\U0000180e\U0000200b-\U0000200f\U0000202a-\U0000202e\U00002060-\U00002064"
    "\U00002066-\U0000206f\U0000feff\U0000fff9-\U0000fffb\U000110bd\U000110cd"
    "\U00013430-\U0001343f\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0001"
    "\U000e0020-\U000e007f]"
)
# Line breaks other than LF that str.splitlines() honours: each becomes one LF.
_LINE_BREAKS = re.compile("\r\n|[\r\x0b\x0c\x1c\x1d\x1e\x85\U00002028\U00002029]")
# Tabs and every Unicode space separator (category Zs: NBSP, thin, narrow, ideographic...).
_SPACE_CHARS = re.compile("[\t\xa0\U00001680\U00002000-\U0000200a\U0000202f\U0000205f\U00003000]")
# Control characters left once tabs and line breaks are mapped (LF is the only one kept).
_CONTROL = re.compile("[\x00-\x09\x0b-\x1f\x7f-\x9f]")
_SPACE_RUN = re.compile(" {2,}")
_BLANK_RUN = re.compile("\n{3,}")


def normalize_text(text: str) -> str:
    """The canonical form of a pasted or extracted text, applied once where it enters the app.

    Two texts that differ only in whitespace, line endings or invisible characters get the same
    result, so they get the same cache key, the same model input and the same line numbers.
    Lone surrogates are dropped; CRLF, CR and the other line breaks become LF; tabs and Unicode
    spaces (NBSP...) become a plain space; format characters (zero-width, BOM, soft hyphen,
    direction marks) and control characters are dropped; then Unicode NFC. Each line loses its
    leading and trailing spaces and runs of spaces become one; 3+ line breaks become 2 (at most
    one blank line); blank lines at both ends are removed. Words, case and punctuation are kept.
    Idempotent: normalizing twice changes nothing.
    """
    # A lone surrogate cannot be encoded as UTF-8: drop it; a valid pair becomes one character.
    text = text.encode("utf-16", "surrogatepass").decode("utf-16", "ignore")
    text = _LINE_BREAKS.sub("\n", text)
    text = _SPACE_CHARS.sub(" ", text)
    text = _CONTROL.sub("", _INVISIBLE.sub("", text))
    # NFC last among the character steps: an invisible joiner can no longer block a composition.
    text = unicodedata.normalize("NFC", text)
    lines = [_SPACE_RUN.sub(" ", line).strip(" ") for line in text.split("\n")]
    return _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip("\n")


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
    """NFKC, straight quotes, plain dashes, regular spaces, collapsed whitespace, no invisible
    format characters. Case kept."""
    text = unicodedata.normalize("NFKC", _INVISIBLE.sub("", text)).translate(_TRANSLATE)
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
