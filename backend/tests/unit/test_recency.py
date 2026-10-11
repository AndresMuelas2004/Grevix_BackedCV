from datetime import date

import pytest

from backedcv.domain.models import (
    CVEntry,
    CVLine,
    Evidence,
    JobPosting,
    ParsedCV,
    RecencyRule,
    Requirement,
    RequirementAssessment,
)
from backedcv.domain.recency import (
    AGING_MAX_YEARS,
    RECENT_MAX_YEARS,
    apply_recency,
    band_for,
    check_recency,
    find_recency_rules,
    line_last_used,
    years_since,
)

TODAY = date(2026, 10, 11)


def req(rid, label, category="hard_skill", importance="required", terms=None):
    return Requirement(
        id=rid,
        label=label,
        quote=label,
        terms=[label] if terms is None else terms,
        category=category,
        importance=importance,
    )


def met(rid, *refs, status="met"):
    return RequirementAssessment(
        requirement_id=rid,
        status=status,
        evidence=[Evidence(ref=ref, quote=f"Quote of {ref}", match_type="exact") for ref in refs],
        keyword_present=True,
    )


def rule(window, *requirement_ids):
    return RecencyRule(
        quote="A sentence of the posting.",
        window_years=window,
        requirement_ids=list(requirement_ids),
    )


def cv_sample() -> ParsedCV:
    """L001 (Kubernetes) and L004 (teamwork) end in 2017-12, L002 (Python) is current,
    L003 (Java) sits in an entry with no dates."""
    return ParsedCV(
        lines=[CVLine(id=f"L00{n}", text=f"Line {n}") for n in range(1, 5)],
        entries=[
            CVEntry(
                id="E1",
                section_id="S1",
                kind="job",
                start="2015-01",
                end="2017-12",
                line_ids=["L001", "L004"],
            ),
            CVEntry(
                id="E2",
                section_id="S1",
                kind="job",
                start="2024-01",
                end="present",
                line_ids=["L002"],
            ),
            CVEntry(id="E3", section_id="S1", kind="job", line_ids=["L003"]),
        ],
    )


JOB = JobPosting(
    requirements=[
        req("R01", "Kubernetes"),
        req("R02", "Python"),
        req("R03", "Java", importance="preferred"),
        req("R04", "Teamwork", category="soft_skill"),
        req("R05", "Five years of experience", category="experience_years"),
        req("R06", "Computer science degree", category="education"),
    ]
)


def test_line_last_used_reads_present_end_and_start_only_entries():
    cv = ParsedCV(
        lines=[CVLine(id=f"L00{n}", text=f"Line {n}") for n in range(1, 6)],
        entries=[
            CVEntry(
                id="E1",
                section_id="S1",
                kind="job",
                start="2020-01",
                end="present",
                line_ids=["L001"],
            ),
            CVEntry(
                id="E2",
                section_id="S1",
                kind="job",
                start="2015-03",
                end="2017-06",
                line_ids=["L002"],
            ),
            CVEntry(id="E3", section_id="S1", kind="job", start="2019-03", line_ids=["L003"]),
            CVEntry(id="E4", section_id="S1", kind="education", line_ids=["L004"]),
        ],
    )

    # L004 has no dates at all and L005 is in no entry: both are absent.
    assert line_last_used(cv, TODAY) == {"L001": "2026-10", "L002": "2017-06", "L003": "2019-03"}


def test_a_line_in_two_entries_keeps_the_latest_whatever_the_order():
    older = CVEntry(
        id="E1", section_id="S1", kind="job", start="2010-01", end="2014-06", line_ids=["L001"]
    )
    newer = CVEntry(
        id="E2", section_id="S1", kind="job", start="2016-01", end="2018-02", line_ids=["L001"]
    )
    line = [CVLine(id="L001", text="Shared line")]

    assert line_last_used(ParsedCV(lines=line, entries=[older, newer]), TODAY) == {
        "L001": "2018-02"
    }
    assert line_last_used(ParsedCV(lines=line, entries=[newer, older]), TODAY) == {
        "L001": "2018-02"
    }


@pytest.mark.parametrize(
    ("ym", "years"),
    [("2026-10", 0.0), ("2026-04", 0.5), ("2017-12", 8.8), ("2016-10", 10.0), ("2027-01", 0.0)],
)
def test_years_since_is_months_over_twelve_to_one_decimal(ym, years):
    assert years_since(ym, TODAY) == years


@pytest.mark.parametrize(
    ("years", "band"),
    [
        (None, "undated"),
        (0.0, "recent"),
        (RECENT_MAX_YEARS, "recent"),
        (3.1, "aging"),
        (AGING_MAX_YEARS, "aging"),
        (6.1, "stale"),
    ],
)
def test_bands_change_at_the_edges(years, band):
    assert band_for(years) == band


@pytest.mark.parametrize(
    ("sentence", "window"),
    [
        ("Experience with Docker within the last 3 years.", 3.0),
        ("Hands-on Docker work in the past five years.", 5.0),
        ("Python experience over the previous ten years.", 10.0),
        ("Java expertise within 2 years.", 2.0),
        ("Some Go work during the last 4 years.", 4.0),
    ],
)
def test_explicit_windows_in_digits_or_number_words(sentence, window):
    rules = find_recency_rules(sentence, JobPosting())

    assert [r.window_years for r in rules] == [window]


def test_five_plus_years_then_a_window_of_seven_years_gives_window_seven():
    text = "We want 5+ years of Python, with recent work in the last 7 years."

    rules = find_recency_rules(text, JobPosting())

    assert [r.window_years for r in rules] == [7.0]
    assert rules[0].quote == text


def test_recent_experience_without_a_number_is_no_rule():
    text = "We value recent experience with Kubernetes. Five years of experience is expected."

    assert find_recency_rules(text, JobPosting()) == []


def test_rules_name_the_requirements_they_mention_and_general_rules_name_none():
    job = JobPosting(
        requirements=[req("R01", "Kubernetes", terms=["Kubernetes", "K8s"]), req("R02", "Python")]
    )
    text = (
        "Hands-on K8s work within the last 3 years.\n"
        "Candidates must have worked in the last 5 years."
    )

    rules = find_recency_rules(text, job)

    assert [(r.quote, r.window_years, r.requirement_ids, r.source) for r in rules] == [
        ("Hands-on K8s work within the last 3 years.", 3.0, ["R01"], "rule"),
        ("Candidates must have worked in the last 5 years.", 5.0, [], "rule"),
    ]


@pytest.mark.parametrize(
    "sentence",
    [
        "Experience with Python within 2 years of graduation.",
        "Candidates who graduated in the last 3 years are preferred.",
        "Python developers within the last 3 years since graduating.",
        "Experience with Python within 2 years of earning your degree.",
        "A bachelor's degree obtained within the last 5 years.",
        "Recent graduates only: within the last 3 years.",
    ],
)
def test_windows_tied_to_graduation_or_a_degree_are_not_recency_rules(sentence):
    job = JobPosting(requirements=[req("R01", "Python")])

    assert find_recency_rules(sentence, job) == []


@pytest.mark.parametrize(
    ("text", "windows"),
    [
        ("Python within the last 3 years, and graduates are welcome.", [3.0]),
        ("Python within the last 3 years, graduated within the last 5 years.", [3.0]),
        ("Recent graduates are welcome.\nPython within the last 3 years.", [3.0]),
    ],
)
def test_a_work_window_survives_a_graduation_window_in_another_clause(text, windows):
    rules = find_recency_rules(text, JobPosting())

    assert [r.window_years for r in rules] == windows


def test_a_degree_window_is_never_a_rule_on_the_degree_requirement():
    job = JobPosting(requirements=[req("R06", "Computer science degree", category="education")])

    assert find_recency_rules("Computer science degree within 2 years of graduation.", job) == []


def test_evidence_inside_the_rule_window_has_no_effect():
    checks = check_recency(JOB, cv_sample(), {"R02": met("R02", "L002")}, [rule(5, "R02")], TODAY)

    check = checks["R02"]
    assert check.effect == "none"
    assert check.within_rule is True
    assert check.band == "recent"
    assert check.last_used == "2026-10"


def test_evidence_outside_the_rule_window_is_downgraded_with_a_plain_sentence():
    checks = check_recency(JOB, cv_sample(), {"R01": met("R01", "L001")}, [rule(5, "R01")], TODAY)

    check = checks["R01"]
    assert check.effect == "downgraded"
    assert check.within_rule is False
    assert check.last_used == "2017-12"
    assert check.years_since == 8.8
    assert check.explanation == (
        "Your most recent Kubernetes evidence is from 2017 (8 years ago); "
        "the posting asks for it within the last 5 years."
    )


def test_stale_evidence_without_a_rule_is_only_a_warning():
    checks = check_recency(JOB, cv_sample(), {"R04": met("R04", "L004")}, [], TODAY)

    check = checks["R04"]
    assert check.effect == "warning"
    assert check.band == "stale"
    assert check.rule is None
    assert check.explanation == (
        "Your most recent Teamwork evidence is from 2017 (8 years ago), which looks outdated."
    )


def test_recent_evidence_without_a_rule_has_no_effect():
    checks = check_recency(JOB, cv_sample(), {"R02": met("R02", "L002")}, [], TODAY)

    assert checks["R02"].effect == "none"
    assert checks["R02"].explanation == (
        "Your most recent Python evidence is from 2026 (less than a year ago)."
    )


def test_undated_evidence_is_a_warning_under_a_rule_and_nothing_without_one():
    partial_java = {"R03": met("R03", "L003", status="partial")}

    with_rule = check_recency(JOB, cv_sample(), partial_java, [rule(5, "R03")], TODAY)["R03"]
    assert with_rule.effect == "warning"
    assert with_rule.band == "undated"
    assert with_rule.last_used is None
    assert with_rule.years_since is None
    assert with_rule.within_rule is None
    assert with_rule.explanation == (
        "Your Java evidence has no dates, so it cannot be shown to be within the last 5 years."
    )

    without_rule = check_recency(JOB, cv_sample(), partial_java, [], TODAY)["R03"]
    assert without_rule.effect == "none"
    assert (
        without_rule.explanation
        == "Your Java evidence has no dates, so its recency cannot be checked."
    )


def test_the_smallest_window_wins():
    assessments = {"R01": met("R01", "L001")}

    general_only = check_recency(JOB, cv_sample(), assessments, [rule(10)], TODAY)["R01"]
    assert general_only.effect == "none"

    both = check_recency(JOB, cv_sample(), assessments, [rule(10), rule(5, "R01")], TODAY)["R01"]
    assert both.rule.window_years == 5
    assert both.effect == "downgraded"


def test_general_rules_reach_only_required_hard_skills_and_experience_years():
    assessments = {
        "R01": met("R01", "L001"),  # required hard skill
        "R03": met("R03", "L003", status="partial"),  # preferred hard skill
        "R04": met("R04", "L004"),  # soft skill
        "R05": met("R05", "L001"),  # required experience_years
        "R06": met("R06", "L001"),  # required education
    }

    checks = check_recency(JOB, cv_sample(), assessments, [rule(5)], TODAY)

    assert checks["R01"].effect == "downgraded"
    assert checks["R05"].effect == "downgraded"
    assert checks["R03"].rule is None
    assert checks["R04"].rule is None
    assert checks["R04"].effect == "warning"  # stale on its own; the general rule did not reach it
    assert "R06" not in checks  # a degree does not expire: no recency check at all


def test_only_met_or_partial_requirements_with_cv_line_evidence_get_a_check():
    assessments = {
        "R01": met("R01", "L001"),
        "R02": met("R02", "L002", status="missing"),
        "R03": met("R03", "F01"),  # a computed fact, not a CV line
        "R04": met("R04"),  # no evidence at all
    }

    assert list(check_recency(JOB, cv_sample(), assessments, [], TODAY)) == ["R01"]


def test_apply_recency_downgrades_to_missing_and_never_mutates_its_input():
    assessments = {"R01": met("R01", "L001"), "R02": met("R02", "L002")}
    before = {rid: a.model_dump() for rid, a in assessments.items()}
    checks = check_recency(JOB, cv_sample(), assessments, [rule(5, "R01"), rule(5, "R02")], TODAY)

    result = apply_recency(assessments, checks)

    assert {rid: a.model_dump() for rid, a in assessments.items()} == before
    assert result["R01"].status == "missing"
    assert result["R01"].rationale == checks["R01"].explanation
    assert result["R01"].keyword_present is True
    assert result["R01"].evidence == assessments["R01"].evidence
    assert result["R01"].evidence is not assessments["R01"].evidence
    assert result["R02"].status == "met"
    assert result["R02"] is not assessments["R02"]
