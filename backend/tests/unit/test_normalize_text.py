"""The canonical form every CV and posting takes when it enters the app (domain/text.py)."""

import sys
import unicodedata

from backedcv.domain.text import fold, normalize_text
from backedcv.ingestion import read_cv_text


def _all_of_category(category: str) -> list[str]:
    return [chr(c) for c in range(sys.maxunicode + 1) if unicodedata.category(chr(c)) == category]


def test_line_endings_become_lf():
    assert (
        normalize_text("a\r\nb\rc\nd\U00002028e\U00002029f\x85g\x0bh\x0ci")
        == "a\nb\nc\nd\ne\nf\ng\nh\ni"
    )


def test_tabs_and_unicode_spaces_become_one_plain_space():
    assert (
        normalize_text("Python\t\xa0and\U00002009SQL\U0000202f\U00003000skills")
        == "Python and SQL skills"
    )


def test_every_unicode_space_separator_becomes_a_plain_space():
    for char in _all_of_category("Zs"):
        assert normalize_text(f"a{char}b") == "a b", hex(ord(char))


def test_invisible_characters_are_dropped():
    text = "\U0000feffPy\U0000200bthon, Kuber\xadnetes and\U0000200d SQL\U00002060\U0000200e"
    assert normalize_text(text) == "Python, Kubernetes and SQL"


def test_every_format_character_is_dropped():
    for char in _all_of_category("Cf"):
        assert normalize_text(f"a{char}b") == "ab", hex(ord(char))


def test_control_characters_are_dropped_but_line_breaks_are_kept():
    assert normalize_text("a\x00b\x1fc\x7fd\ne") == "abcd\ne"


def test_spaces_at_line_ends_go_and_runs_of_spaces_collapse():
    assert (
        normalize_text("  About the role   \n- Python  and   SQL  ")
        == "About the role\n- Python and SQL"
    )


def test_blank_lines_collapse_to_one_and_vanish_at_both_ends():
    assert normalize_text("\n\n \nTitle\n\n\n\n \nBody\n\n") == "Title\n\nBody"
    assert normalize_text("Title\n\nBody") == "Title\n\nBody"  # one blank line is kept


def test_nfc_composes_even_across_an_invisible_joiner():
    assert normalize_text("José") == "José"
    assert normalize_text("Jose\U0000200d́") == "José"


def test_words_case_and_punctuation_are_kept():
    text = "C++, C#, .NET and Node.js — “quoted” (C1 or higher); 3.5 years: OK!"
    assert normalize_text(text) == text


def test_a_lone_surrogate_is_dropped():
    assert normalize_text("ok\ud800 done") == "ok done"


def test_idempotent():
    samples = [
        "\n  Junior AI Engineer\r\n\r\n\r\nAbout the role \t\n- Python\xa0 and\U0000200b SQL  \n\n",
        "e\U0000200d́ \U00002028 x\U00003000\U00003000y\r",
        "",
        "\n\n\n",
    ]
    for text in samples:
        once = normalize_text(text)
        assert normalize_text(once) == once


def test_fold_ignores_invisible_characters_too():
    assert fold("Lang\U0000200dGraph\U0000feff and Py\U00002060thon") == "LangGraph and Python"


def test_a_pasted_cv_gets_the_same_lines_whatever_its_whitespace():
    clean = "Jane Doe\nEXPERIENCE\nBuilt ETL pipelines in Python\nSKILLS\nPython, SQL"
    messy = (
        "\U0000feff\r\n  Jane\xa0Doe  \r\n\r\n\r\nEXPERIENCE\t\r\n"
        "Built ETL\U0000200b pipelines in  Python\r\nSKILLS \r\nPython,\U00002009SQL\r\n\r\n"
    )
    assert read_cv_text(messy).lines == read_cv_text(clean).lines
