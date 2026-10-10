import pytest

from backedcv.domain.keywords import contains_term, keyword_hits, keyword_present
from backedcv.domain.models import CVLine, Requirement


@pytest.mark.parametrize(
    ("text", "term", "expected"),
    [
        ("Built services in C++ and Python", "C++", True),
        ("Built services in C and Python", "C++", False),
        ("Wrote C++ code", "C", False),
        ("Backend in C#/.NET", "C#", True),
        ("Backend in C#/.NET", ".NET", True),
        ("APIs with Node.js.", "Node.js", True),
        ("Machine-learning pipelines", "machine learning", True),
        ("Managed a team of four", "manage", True),
        ("He goes to work", "Go", False),
        ("Wrote services in Go", "Go", True),
        ("Docker containers", "dockers", False),
        ("CI/CD with GitHub Actions", "CI/CD", True),
        ("Kubernetes clusters", "kubernetes clusters", True),
    ],
)
def test_contains_term(text, term, expected):
    assert contains_term(text, term) is expected


def _req(**kwargs):
    base = {
        "id": "R01",
        "label": "Python",
        "quote": "Strong Python",
        "category": "hard_skill",
        "importance": "required",
    }
    return Requirement(**(base | kwargs))


def test_keyword_hits_separates_exact_and_alias():
    lines = [CVLine(id="L001", text="Python developer"), CVLine(id="L002", text="Used py3 daily")]
    req = _req(terms=["Python"], aliases=["py3"])

    hits = keyword_hits(req, lines)

    assert [(h.line_id, h.match_type) for h in hits] == [("L001", "exact"), ("L002", "alias")]


def test_keyword_present_needs_a_literal_term():
    lines = [CVLine(id="L001", text="Built agent frameworks")]

    assert keyword_present(_req(terms=["LangChain"]), lines) is False
    assert keyword_present(_req(terms=["agent frameworks"]), lines) is True
