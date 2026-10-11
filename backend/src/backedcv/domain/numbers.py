"""Numbers in CVs and rewrites, normalized so that "1,200", "1.200" and "1200" compare equal."""

import re

from backedcv.domain.text import fold_lower

_WORDS: dict[str, str] = {
    # English. "one" is left out on purpose: it is also a pronoun ("one of the teams").
    "zero": "0", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "thirteen": "13", "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20",
    # Spanish. "uno", "una" and "un" are left out on purpose: they are articles too.
    "cero": "0", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6",
    "siete": "7", "ocho": "8", "nueve": "9", "diez": "10", "once": "11", "doce": "12",
    "trece": "13", "catorce": "14", "quince": "15", "dieciséis": "16", "dieciseis": "16",
    "diecisiete": "17", "dieciocho": "18", "diecinueve": "19", "veinte": "20",
}  # fmt: skip
_WORD = re.compile(r"(?<!\w)(" + "|".join(sorted(_WORDS, key=len, reverse=True)) + r")(?!\w)")
# A digit run glued to a letter ("S3", "Python3") is a name, not a quantity, so it is skipped.
_NUMBER = re.compile(r"(?<!\w)[0-9]+(?:[.,][0-9]+)*")
# A separator followed by exactly three digits is a thousands separator ("1.200" is 1200);
# any other separator is a decimal point ("1,5" and "1.25" are decimals).
_PLAIN = re.compile(r"([0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+)(?:[.,]([0-9]+))?")


def _canonical(token: str) -> set[str]:
    plain = _PLAIN.fullmatch(token)
    if plain is None:  # not one number, e.g. a version "3.2.1": each digit run counts alone
        return {run.lstrip("0") or "0" for run in re.findall(r"[0-9]+", token)}
    whole, fraction = plain.group(1), (plain.group(2) or "").rstrip("0")
    integer = re.sub(r"[.,]", "", whole).lstrip("0") or "0"
    return {f"{integer}.{fraction}" if fraction else integer}


def extract_numbers(text: str) -> set[str]:
    """Canonical numbers in text: separators dropped, % ignored, number words as digits."""
    folded = fold_lower(text)
    numbers: set[str] = set()
    for match in _NUMBER.finditer(folded):
        numbers |= _canonical(match.group())
    numbers.update(_WORDS[match.group(1)] for match in _WORD.finditer(folded))
    return numbers
