import pytest

from backedcv.domain.guards import apply_guards, covered_requirements, introduced_terms, run_guards
from backedcv.domain.models import (
    ComputedFact,
    CVEntry,
    CVLine,
    CVSection,
    GuardResult,
    JobPosting,
    ParsedCV,
    Requirement,
    Suggestion,
)

ORIGINAL = "Cut infrastructure costs by 35% using Docker and Kubernetes"
FAITHFUL = "Reduced infrastructure costs by 35% using Docker and Kubernetes"
SUMMARY = "Backend engineer who ships reliable services Works mostly with Docker and Kubernetes"

CV = ParsedCV(
    lines=[
        CVLine(id="L001", text="Jane Doe"),
        CVLine(id="L002", text="Profile"),
        CVLine(id="L003", text="Senior Backend Engineer at Acme Corp"),
        CVLine(id="L004", text=ORIGINAL),
        CVLine(id="L005", text="Led a team of 5 engineers"),
        CVLine(id="L006", text="Backend engineer who ships reliable services"),
        CVLine(id="L007", text="Works mostly with Docker and Kubernetes"),
    ],
    facts=[ComputedFact(id="F01", text="Total experience: 6 years", derived_from=["L003"])],
    sections=[
        CVSection(id="S01", heading_line_id="L002", type="summary", line_ids=["L006", "L007"]),
        CVSection(
            id="S02", heading_line_id=None, type="experience", line_ids=["L003", "L004", "L005"]
        ),
        CVSection(id="S03", heading_line_id=None, type="skills", line_ids=[]),
    ],
    entries=[
        CVEntry(
            id="E01",
            section_id="S02",
            kind="job",
            title="Senior Backend Engineer",
            organization="Acme Corp",
            line_ids=["L003"],
        ),
    ],
)

# A CV with nothing but a name, so every technical word in a test is new to it.
BARE = ParsedCV(lines=[CVLine(id="L001", text="Jane Doe")])

JOB = JobPosting(
    title="Staff Platform Engineer",
    company="Globex",
    requirements=[
        Requirement(
            id="R01",
            label="Kubernetes",
            quote="Kubernetes",
            category="hard_skill",
            importance="required",
            terms=["Kubernetes"],
        ),
        Requirement(
            id="R02",
            label="Python",
            quote="Python",
            category="hard_skill",
            importance="preferred",
            terms=["Python"],
            aliases=["py"],
        ),
    ],
)


# A CV whose computed total is 3.2 years over three jobs, as the parser computes it.
TOTAL_CV = ParsedCV(
    lines=[
        CVLine(id="L001", text="Jane Doe"),
        CVLine(id="L002", text="Data engineer who builds data pipelines and small LLM tools."),
        CVLine(id="L003", text="Data Engineer, Pellmark Retail Group, Valencia"),
        CVLine(id="L004", text="Built Python ETL jobs that load 2 million rows a day."),
        CVLine(id="L005", text="Delivered 3 pilot projects for retail teams."),
    ],
    facts=[
        ComputedFact(
            id="F01",
            text="Total professional experience: 3.2 years (computed from the dates of 3 jobs)",
            derived_from=["L003"],
        )
    ],
    sections=[
        CVSection(id="S01", heading_line_id=None, type="summary", line_ids=["L002"]),
        CVSection(
            id="S02", heading_line_id=None, type="experience", line_ids=["L003", "L004", "L005"]
        ),
    ],
)
TOTAL_DETAIL = (
    "A computed total (F01) covers the whole CV; "
    "it cannot be attached to one role, skill or employer."
)


def _align(after, **changes):
    base = {
        "id": "S01",
        "kind": "align_wording",
        "target": "L004",
        "before": ORIGINAL,
        "after": after,
        "requirement_ids": ["R01"],
        "cited_refs": ["L004"],
    }
    return Suggestion(**(base | changes))


def _guard(s, name, job=JOB) -> GuardResult:
    return next(g for g in run_guards(s, CV, job) if g.name == name)


def test_faithful_rewording_passes_every_guard():
    guards = run_guards(_align(FAITHFUL), CV, JOB)

    assert [g.name for g in guards] == [
        "ids_exist",
        "cites_evidence",
        "numbers_backed",
        "fact_scope",
        "no_posting_entities",
        "length",
        "introduced_terms",
    ]
    assert all(g.ok for g in guards)
    assert guards[-1].detail is None


@pytest.mark.parametrize(
    ("changes", "ok"),
    [
        ({}, True),
        ({"target": "L999"}, False),
        ({"cited_refs": ["L004", "L404"]}, False),
        ({"requirement_ids": ["R09"]}, False),
    ],
)
def test_ids_exist(changes, ok):
    assert _guard(_align(FAITHFUL, **changes), "ids_exist").ok is ok


@pytest.mark.parametrize(
    ("kind", "target", "ok"),
    [
        ("add_skill", "S03", True),
        ("add_skill", "new-skills", True),
        ("add_skill", "L004", False),
        ("tailor_summary", "S01", True),
        ("tailor_summary", "new-summary", True),
        ("tailor_summary", "S02", False),
        ("align_wording", "new-skills", False),
    ],
)
def test_ids_exist_depends_on_the_kind(kind, target, ok):
    s = Suggestion(id="S02", kind=kind, target=target, after="Terraform", cited_refs=["L004"])
    assert _guard(s, "ids_exist").ok is ok


def test_cites_evidence_needs_a_reference():
    assert _guard(_align(FAITHFUL), "cites_evidence").ok is True
    assert _guard(_align(FAITHFUL, cited_refs=[]), "cites_evidence").ok is False


def test_numbers_must_come_from_the_cited_lines_or_the_original():
    assert _guard(_align("Reduced costs by 35%"), "numbers_backed").ok is True

    fake = _guard(_align("Cut costs by 40%"), "numbers_backed")
    assert fake.ok is False
    assert "40" in fake.detail


def test_number_words_count_as_numbers():
    s = _align(
        "Led a team of five engineers",
        target="L005",
        cited_refs=["L005"],
        before="Led a team of 5 engineers",
    )
    assert _guard(s, "numbers_backed").ok is True


def test_posting_title_or_company_in_a_bullet_fails():
    company = _guard(_align("Reduced costs at Globex by 35%"), "no_posting_entities")
    assert company.ok is False
    assert "Globex" in company.detail

    title = _guard(_align("Reduced costs as Staff Platform Engineer by 35%"), "no_posting_entities")
    assert title.ok is False


def test_posting_name_is_fine_when_a_cv_entry_already_has_it():
    acme_job = JOB.model_copy(update={"company": "Acme Corp"})
    s = _align("Reduced costs at Acme Corp by 35%")

    assert _guard(s, "no_posting_entities", acme_job).ok is True


def test_tailor_summary_may_name_the_posting():
    s = Suggestion(
        id="S02",
        kind="tailor_summary",
        target="S01",
        after="Engineer at Globex with Kubernetes",
        cited_refs=["L003"],
    )
    assert _guard(s, "no_posting_entities").ok is True


def test_length_is_twice_the_original_plus_thirty_words():
    # ORIGINAL has 9 words, so the limit is 48.
    assert _guard(_align("built " * 48), "length").ok is True
    assert _guard(_align("built " * 49), "length").ok is False


def test_length_of_an_added_line_allows_thirty_words():
    added = Suggestion(
        id="S02", kind="add_skill", target="S03", after="built " * 30, cited_refs=["L004"]
    )
    assert _guard(added, "length").ok is True
    assert _guard(added.model_copy(update={"after": "built " * 31}), "length").ok is False


def test_introduced_terms_is_a_soft_flag():
    s = _align("Reduced infrastructure costs by 35% using Terraform and Kubernetes")
    result = _guard(s, "introduced_terms")

    assert (result.ok, result.hard, result.detail) == (True, False, "Terraform")


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        ("Reduced costs using Docker and Kubernetes", []),
        ("Terraform shipped daily", ["Terraform"]),  # a technical name is checked even at the start
        ("Used Docker and Rust", ["Rust"]),
        ("Built Node.js services", ["Node.js"]),
        ("Deployed on AWS", ["AWS"]),
        ("Used KUBERNETES daily", []),  # matches the CV's "Kubernetes" in any case
        ("Cut costs by 40%", ["40"]),  # "Cut" is in the CV, so only the number is new
        ("Led a team of 5 engineers", []),
    ],
)
def test_introduced_terms(after, expected):
    assert introduced_terms(after, CV) == expected


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        ("Terraform, Docker", ["Terraform", "Docker"]),
        ("Kubernetes clusters", ["Kubernetes"]),  # ends in -s, but it is on the tech list
        ("Redis caches results", ["Redis"]),
        ("Reduced costs", []),  # -ed
        ("Led teams", []),  # on the starter list
        ("Designs systems", []),  # -s
        ("Using tools", []),  # on the starter list
        ("Implementing systems", []),  # -ing
        ("Design systems", ["Design"]),  # base verbs are on neither list, so they are checked
    ],
)
def test_sentence_start_is_exempt_only_for_ordinary_words(after, expected):
    assert introduced_terms(after, BARE) == expected


def test_covered_requirements_match_terms_and_aliases():
    assert covered_requirements("Built services on Kubernetes", JOB) == ["R01"]
    assert covered_requirements("Wrote py scripts", JOB) == ["R02"]
    assert covered_requirements("Built services", JOB) == []


def test_apply_guards_fills_the_original_and_the_computed_fields():
    s = _align(FAITHFUL, before=None)
    result = apply_guards(s, CV, JOB)

    assert result.before == ORIGINAL
    assert result.covers_requirement_ids == ["R01"]
    assert result.introduced_terms == []
    assert result.verification.status == "pending"
    assert result.verification.reason is None
    assert len(result.verification.guards) == 7
    assert s.before is None  # the input is not changed


def test_apply_guards_marks_a_hard_failure_unsupported_with_the_first_reason():
    result = apply_guards(_align("Reduced costs by 40% at Globex"), CV, JOB)
    numbers = next(g for g in result.verification.guards if g.name == "numbers_backed")

    assert result.verification.status == "unsupported"
    assert result.verification.reason == numbers.detail


def test_apply_guards_reports_a_missing_target_first():
    result = apply_guards(_align(FAITHFUL, target="L999"), CV, JOB)

    assert result.verification.status == "unsupported"
    assert result.verification.reason == "target L999 does not exist"


def test_apply_guards_keeps_soft_flags_pending():
    s = _align("Reduced infrastructure costs by 35% using Terraform and Kubernetes")
    result = apply_guards(s, CV, JOB)

    assert result.introduced_terms == ["Terraform"]
    assert result.verification.status == "pending"
    assert result.verification.reason is None


def test_existing_summary_is_filled_from_its_lines_in_order():
    s = Suggestion(
        id="S02",
        kind="tailor_summary",
        target="S01",
        before="invented",
        after="Backend engineer with Docker and Kubernetes",
        cited_refs=["L006"],
    )
    filled = apply_guards(s, CV, JOB)

    assert filled.before == SUMMARY
    # The original summary has 12 words, so the limit is 54.
    assert _guard(filled.model_copy(update={"after": "built " * 54}), "length").ok is True
    assert _guard(filled.model_copy(update={"after": "built " * 55}), "length").ok is False


def test_added_skill_has_no_original_so_its_numbers_must_be_cited():
    s = Suggestion(
        id="S02",
        kind="add_skill",
        target="S03",
        before="invented 40",
        after="Terraform 40",
        cited_refs=["L004"],
    )
    filled = apply_guards(s, CV, JOB)

    assert filled.before is None
    assert _guard(filled, "numbers_backed").ok is False  # 40 is not in L004 (which says 35)


def test_new_summary_has_no_original_and_allows_sixty_words():
    s = Suggestion(
        id="S02",
        kind="tailor_summary",
        target="new-summary",
        before="invented",
        after="built " * 60,
        cited_refs=["L004"],
    )
    filled = apply_guards(s, CV, JOB)

    assert filled.before is None
    assert _guard(filled, "length").ok is True
    assert _guard(filled.model_copy(update={"after": "built " * 61}), "length").ok is False


def _summary(after, cited_refs=("F01",), before=None) -> Suggestion:
    return Suggestion(
        id="S02",
        kind="tailor_summary",
        target="S01",
        before=before,
        after=after,
        cited_refs=list(cited_refs),
    )


def _total_guard(s, name) -> GuardResult:
    return next(g for g in run_guards(s, TOTAL_CV, JOB) if g.name == name)


@pytest.mark.parametrize(
    "after",
    [
        "Data engineer with 3.2 years of experience building Python data pipelines",  # C09
        "Worked 3.2 years as a data engineer",
        "Built ETL jobs for 3.2 years of experience with Python",
        "Worked 3.2 years in data engineering",
        "Over 3 years of Python",
    ],
)
def test_a_total_attached_to_a_role_skill_or_employer_fails(after):
    result = _total_guard(_summary(after), "fact_scope")

    assert result.ok is False
    assert result.detail == TOTAL_DETAIL


@pytest.mark.parametrize(
    "after",
    [
        "3.2 years of experience",
        "3.2 years of professional experience",
        "3.2 years of total experience",
        "3.2 years' experience",
        "3.2 years experience",
        "+3.2 years of experience",
        "Over 3.2 years of experience",
        "More than 3.2 years of experience",
        "About 3.2 years of experience.",
        "3.2+ years of experience overall",
    ],
)
def test_the_total_keeps_its_own_scope(after):
    assert _total_guard(_summary(after), "fact_scope").ok is True


def test_a_rounded_total_passes_because_three_is_also_in_the_fact_text():
    # F01 also says "3 jobs", so "3" is backed by it and numbers_backed accepts it.
    s = _summary("Over 3 years of experience")

    assert _total_guard(s, "numbers_backed").ok is True
    assert _total_guard(s, "fact_scope").ok is True


def test_a_number_a_cited_line_also_states_is_not_checked_for_scope():
    # "3" is on L005 as well as in F01: with L005 cited the line backs it, so the scope is free.
    after = "Delivered 3 pilot projects for retail teams"

    assert _total_guard(_summary(after, cited_refs=["L005", "F01"]), "fact_scope").ok is True
    assert _total_guard(_summary(after), "fact_scope").ok is False


def test_a_number_the_original_already_states_is_not_checked_for_scope():
    s = _summary("3.2 years as a data engineer", before="Worked 3.2 years as a data engineer")

    assert _total_guard(s, "fact_scope").ok is True


def test_apply_guards_blocks_the_c09_pattern_with_the_scope_reason():
    s = _summary("Data engineer with 3.2 years of experience building Python data pipelines")
    result = apply_guards(s, TOTAL_CV, JOB)

    assert result.verification.status == "unsupported"
    assert result.verification.reason == TOTAL_DETAIL
