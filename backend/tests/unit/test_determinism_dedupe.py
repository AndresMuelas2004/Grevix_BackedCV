"""Deterministic clean-up of the extracted requirements (domain/dedupe.py)."""

from backedcv.domain.dedupe import canonical_requirements, posting_units
from backedcv.domain.models import JobPosting, Requirement

POSTING = """Junior AI Engineer at Lanternfield Analytics
About the role
We ship LLM assistants. You will pair with senior engineers every day.

Requirements
- Strong Python and SQL skills.
- 5+ years of hands-on experience with LangGraph.
- Experience with AWS is a plus.
- Able to work on-site in our New York office.

Nice to have
- Working knowledge of Docker and FastAPI.
- Must be fluent in English.
Location: New York office, on-site."""


def _req(rid, label, quote, terms=(), category="hard_skill", importance="required", **kw):
    return Requirement(
        id=rid,
        label=label,
        quote=quote,
        terms=list(terms),
        category=category,
        importance=importance,
        **kw,
    )


def _labels(job: JobPosting) -> list[tuple[str, str, str]]:
    return [(r.id, r.label, r.importance) for r in job.requirements]


def test_langgraph_twice_becomes_one_requirement_with_the_strictest_years():
    quote = "5+ years of hands-on experience with LangGraph."
    job = JobPosting(
        requirements=[
            _req("R01", "LangGraph", quote, ["LangGraph"], importance="preferred"),
            _req(
                "R02",
                "5+ years of LangGraph",
                quote,
                ["LangGraph"],
                category="experience_years",
                knockout_type="experience_years",
                min_years=5,
            ),
            _req("R03", "LangGraph experience", quote, ["LangGraph"], min_years=2),
        ]
    )
    [merged] = canonical_requirements(job, POSTING).requirements
    assert merged.id == "R01"
    assert merged.label == "5+ years of LangGraph"
    assert (merged.category, merged.importance, merged.min_years) == (
        "experience_years",
        "required",
        5,
    )
    assert merged.knockout_type == "experience_years"


def test_the_same_label_from_two_bullets_is_kept_once():
    job = JobPosting(
        requirements=[
            _req("R01", "Data pipelines", "Strong Python and SQL skills."),
            _req("R02", "data  pipelines!", "Working knowledge of Docker and FastAPI."),
        ]
    )
    assert len(canonical_requirements(job, POSTING).requirements) == 1


def test_different_categories_with_the_same_term_are_not_merged():
    job = JobPosting(
        requirements=[
            _req("R01", "English", "Must be fluent in English.", ["English"], category="language"),
            _req("R02", "English docs", "Must be fluent in English.", ["English"]),
        ]
    )
    assert len(canonical_requirements(job, POSTING).requirements) == 2


def test_two_location_gates_with_the_same_place_ask_one_question():
    job = JobPosting(
        requirements=[
            _req(
                "R01",
                "On-site in New York",
                "Able to work on-site in our New York office.",
                ["New York"],
                category="location",
            ),
            _req(
                "R02",
                "New York office",
                "Location: New York office, on-site.",
                ["New York"],
                category="location",
            ),
        ]
    )
    assert [r.label for r in canonical_requirements(job, POSTING).requirements] == [
        "On-site in New York"
    ]


def test_order_and_ids_follow_the_posting_whatever_the_model_order():
    reqs = [
        _req("R01", "FastAPI", "Working knowledge of Docker and FastAPI.", ["FastAPI"]),
        _req("R02", "SQL", "Strong Python and SQL skills.", ["SQL"]),
        _req("R03", "Docker", "Working knowledge of Docker and FastAPI.", ["Docker"]),
        _req("R04", "Python", "Strong Python and SQL skills.", ["Python"]),
    ]
    expected = ["Python", "SQL", "Docker", "FastAPI"]
    for order in (reqs, list(reversed(reqs)), [reqs[2], reqs[0], reqs[3], reqs[1]]):
        job = canonical_requirements(JobPosting(requirements=order), POSTING)
        assert [r.label for r in job.requirements] == expected
        assert [r.id for r in job.requirements] == ["R01", "R02", "R03", "R04"]


def test_items_of_one_bullet_share_a_unit_and_other_bullets_do_not():
    job = canonical_requirements(
        JobPosting(
            requirements=[
                _req("R01", "Python", "Strong Python and SQL skills.", ["Python"]),
                _req("R02", "SQL", "SQL skills", ["SQL"]),  # a shorter quote of the same bullet
                _req("R03", "Docker", "Working knowledge of Docker and FastAPI.", ["Docker"]),
            ]
        ),
        POSTING,
    )
    python, sql, docker = job.requirements
    assert python.source_unit is not None and python.source_unit == sql.source_unit
    assert docker.source_unit not in (None, python.source_unit)


def test_sentences_of_one_paragraph_are_separate_units():
    _, units = posting_units("About the role\nWe ship LLM assistants. You will pair with seniors.")
    assert [u.text for u in units] == [
        "about the role",
        "we ship llm assistants.",
        "you will pair with seniors.",
    ]


def test_importance_follows_the_section_and_the_bullet_wording():
    job = canonical_requirements(
        JobPosting(
            requirements=[
                _req(
                    "R01",
                    "Python",
                    "Strong Python and SQL skills.",
                    ["Python"],
                    "hard_skill",
                    "preferred",
                ),
                _req("R02", "AWS", "Experience with AWS is a plus.", ["AWS"]),
                _req("R03", "Docker", "Working knowledge of Docker and FastAPI.", ["Docker"]),
                _req(
                    "R04",
                    "English",
                    "Must be fluent in English.",
                    ["English"],
                    "language",
                    "preferred",
                ),
            ]
        ),
        POSTING,
    )
    assert [(r.label, r.importance) for r in job.requirements] == [
        ("Python", "required"),  # under "Requirements"
        ("AWS", "preferred"),  # "is a plus" wins over the section
        ("Docker", "preferred"),  # under "Nice to have"
        ("English", "required"),  # "Must" wins over the section
    ]
    assert job.requirements[0].cue == "Requirements"


def test_mixed_cues_leave_the_model_importance():
    posting = "Requirements\n- Python is required and Go is a plus."
    job = canonical_requirements(
        JobPosting(
            requirements=[
                _req(
                    "R01",
                    "Go",
                    "Python is required and Go is a plus.",
                    ["Go"],
                    "hard_skill",
                    "preferred",
                ),
            ]
        ),
        posting,
    )
    assert job.requirements[0].importance == "preferred"


def test_an_inline_label_sets_the_section():
    posting = "Requirements:\n- Strong SQL.\nNice to have: experience with dbt.\n- Spark."
    job = canonical_requirements(
        JobPosting(
            requirements=[
                _req("R01", "dbt", "experience with dbt", ["dbt"]),
                _req("R02", "Spark", "Spark.", ["Spark"]),
                _req("R03", "SQL", "Strong SQL.", ["SQL"], importance="preferred"),
            ]
        ),
        posting,
    )
    assert _labels(job) == [
        ("R01", "SQL", "required"),
        ("R02", "dbt", "preferred"),
        ("R03", "Spark", "preferred"),
    ]


def test_a_bullet_that_starts_like_a_heading_is_not_one():
    posting = "Nice to have\n- Requirements gathering with stakeholders\n- Kafka"
    job = canonical_requirements(
        JobPosting(requirements=[_req("R01", "Kafka", "Kafka", ["Kafka"])]), posting
    )
    assert job.requirements[0].importance == "preferred"


def test_an_unknown_heading_ends_the_section_before_it():
    posting = (
        "Nice to have\n- Kafka.\n\nGood to know\nWe use Jira daily.\n"
        "This role requires travel to Austin."
    )
    job = canonical_requirements(
        JobPosting(
            requirements=[
                _req("R01", "Kafka", "Kafka.", ["Kafka"]),
                _req("R02", "Jira", "We use Jira daily.", ["Jira"]),
                _req(
                    "R03",
                    "Travel",
                    "This role requires travel to Austin.",
                    [],
                    "availability",
                    "preferred",
                ),
            ]
        ),
        posting,
    )
    assert [(r.label, r.importance) for r in job.requirements] == [
        ("Kafka", "preferred"),  # the "Nice to have" section
        ("Jira", "required"),  # no section: the model's reading stays
        ("Travel", "required"),  # "requires" in the sentence
    ]


def test_a_quote_not_in_the_posting_has_no_unit_and_comes_last():
    job = canonical_requirements(
        JobPosting(
            requirements=[
                _req(
                    "R01",
                    "Visa",
                    "Not in the posting at all",
                    category="work_authorization",
                    quote_located=False,
                ),
                _req("R02", "Python", "Strong Python and SQL skills.", ["Python"]),
            ]
        ),
        POSTING,
    )
    assert [(r.label, r.source_unit is None) for r in job.requirements] == [
        ("Python", False),
        ("Visa", True),
    ]


def test_canonical_requirements_is_stable_when_applied_twice():
    reqs = [
        _req("R01", "FastAPI", "Working knowledge of Docker and FastAPI.", ["FastAPI"]),
        _req("R02", "LangGraph", "5+ years of hands-on experience with LangGraph.", ["LangGraph"]),
        _req("R03", "Python", "Strong Python and SQL skills.", ["Python"]),
    ]
    once = canonical_requirements(JobPosting(requirements=reqs), POSTING)
    assert canonical_requirements(once, POSTING) == once
