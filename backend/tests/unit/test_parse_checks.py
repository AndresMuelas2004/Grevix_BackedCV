from backedcv.domain.models import (
    Contact,
    ContactField,
    CVEntry,
    CVLine,
    CVSection,
    ParsedCV,
)
from backedcv.domain.parse_checks import run_parse_checks
from backedcv.domain.recruiter_tips import recruiter_tips

MB = 1024 * 1024


def _baseline() -> ParsedCV:
    """A CV that triggers no parse check."""
    lines = [
        CVLine(id="L001", text="Jane Doe"),
        CVLine(id="L002", text="jane@example.com"),
        CVLine(id="L003", text="Experience", bold=True),
        CVLine(id="L004", text="Data Engineer, Acme Corp"),
        CVLine(id="L005", text="Jan 2020 - Present"),
        CVLine(id="L006", text="Built ETL pipelines that cut report time by 40%"),
        CVLine(id="L007", text="Led a team of 4 analysts through the warehouse move"),
        CVLine(id="L008", text="Automated 12 manual checks with Python scripts"),
        CVLine(id="L009", text="Education", bold=True),
        CVLine(id="L010", text="BSc Computer Science, University of Madrid"),
        CVLine(id="L011", text="Jun 2012 - Jun 2016"),
        CVLine(id="L012", text="Skills", bold=True),
        CVLine(id="L013", text="Python, SQL, Docker"),
    ]
    sections = [
        CVSection(
            id="S01",
            heading_line_id="L003",
            type="experience",
            line_ids=["L003", "L004", "L005", "L006", "L007", "L008"],
        ),
        CVSection(id="S02", heading_line_id="L009", type="education", line_ids=["L009", "L010"]),
        CVSection(id="S03", heading_line_id="L012", type="skills", line_ids=["L012", "L013"]),
    ]
    entries = [
        CVEntry(
            id="E01",
            section_id="S01",
            kind="job",
            title="Data Engineer",
            organization="Acme Corp",
            start="2020-01",
            end="present",
            date_source="parser",
            line_ids=["L004", "L005", "L006", "L007", "L008"],
        )
    ]
    contact = Contact(
        name=ContactField(value="Jane Doe", line_id="L001"),
        email=ContactField(value="jane@example.com", line_id="L002"),
    )
    return ParsedCV(
        lines=lines, sections=sections, entries=entries, contact=contact, total_years=5.0
    )


def _older_job() -> CVEntry:
    return CVEntry(
        id="E00",
        section_id="S01",
        kind="job",
        title="Intern",
        organization="Beta Inc",
        start="2014-01",
        end="2015-06",
        date_source="parser",
        line_ids=["L010", "L011"],
    )


def _line(cv: ParsedCV, line_id: str) -> CVLine:
    return next(line for line in cv.lines if line.id == line_id)


def _codes(warnings) -> list[str]:
    return [warning.code for warning in warnings]


def _find(warnings, code: str):
    return next((warning for warning in warnings if warning.code == code), None)


def test_baseline_cv_has_no_parse_warnings():
    assert run_parse_checks(_baseline()) == []


def test_contact_only_in_header_is_flagged():
    cv = _baseline()
    _line(cv, "L002").source = "header"

    warning = _find(run_parse_checks(cv), "contact_outside_body")

    assert warning is not None
    assert warning.severity == "warning"
    assert warning.line_ids == ["L002"]


def test_contact_repeated_in_the_body_is_not_flagged():
    cv = _baseline()
    _line(cv, "L002").source = "header"
    cv.lines.append(CVLine(id="L014", text="Contact: jane@example.com"))

    assert "contact_outside_body" not in _codes(run_parse_checks(cv))


def test_unusual_heading_is_flagged():
    cv = _baseline()
    _line(cv, "L003").text = "Work Stuff"

    warning = _find(run_parse_checks(cv), "nonstandard_heading")

    assert warning is not None
    assert warning.severity == "info"
    assert warning.line_ids == ["L003"]


def test_common_heading_variant_is_not_flagged():
    cv = _baseline()
    _line(cv, "L003").text = "Work Experience:"

    assert "nonstandard_heading" not in _codes(run_parse_checks(cv))


def test_missing_core_sections_are_flagged():
    cv = _baseline()
    cv.sections = []

    warning = _find(run_parse_checks(cv), "missing_section")

    assert warning is not None
    assert warning.severity == "warning"


def test_skills_alone_count_as_a_core_section():
    cv = _baseline()
    cv.sections = [cv.sections[2]]

    assert "missing_section" not in _codes(run_parse_checks(cv))


def test_job_without_start_date_is_flagged():
    cv = _baseline()
    cv.entries[0].start = None

    warning = _find(run_parse_checks(cv), "unreadable_dates")

    assert warning is not None
    assert warning.severity == "warning"
    assert warning.line_ids == ["L004", "L005", "L006", "L007", "L008"]


def test_jobs_listed_oldest_first_are_flagged():
    cv = _baseline()
    cv.entries.insert(0, _older_job())

    warning = _find(run_parse_checks(cv), "not_reverse_chronological")

    assert warning is not None
    assert warning.severity == "info"
    assert warning.line_ids == ["L004", "L005", "L006", "L007", "L008"]


def test_jobs_listed_newest_first_are_not_flagged():
    cv = _baseline()
    cv.entries.append(_older_job())

    assert "not_reverse_chronological" not in _codes(run_parse_checks(cv))


def test_multi_column_flag_is_reported_only_when_set():
    warning = _find(run_parse_checks(_baseline(), multi_column=True), "multi_column")

    assert warning is not None
    assert warning.severity == "warning"
    assert "multi_column" not in _codes(run_parse_checks(_baseline()))


def test_table_lines_are_reported():
    cv = _baseline()
    _line(cv, "L013").source = "table"

    warning = _find(run_parse_checks(cv), "tables")

    assert warning is not None
    assert warning.severity == "info"
    assert warning.line_ids == ["L013"]


def test_letter_spaced_heading_is_flagged():
    cv = _baseline()
    _line(cv, "L003").text = "E X P E R I E N C E"

    warning = _find(run_parse_checks(cv), "letter_spaced")

    assert warning is not None
    assert warning.severity == "warning"
    assert warning.line_ids == ["L003"]


def test_large_file_is_reported_above_2_5_mb():
    cv = _baseline()

    warning = _find(run_parse_checks(cv, file_size=3 * MB), "large_file")

    assert warning is not None
    assert warning.severity == "info"
    assert "large_file" not in _codes(run_parse_checks(cv, file_size=2 * MB))
    assert "large_file" not in _codes(run_parse_checks(cv))


def _experience_cv(bullets: list[str]) -> ParsedCV:
    lines = [
        CVLine(id="L001", text="Data Engineer, Acme Corp"),
        CVLine(id="L002", text="Jan 2020 - Present"),
    ]
    lines += [CVLine(id=f"L{i:03d}", text=text) for i, text in enumerate(bullets, start=3)]
    entry = CVEntry(
        id="E01",
        section_id="S01",
        kind="job",
        title="Data Engineer",
        start="2020-01",
        end="present",
        date_source="parser",
        line_ids=[line.id for line in lines],
    )
    return ParsedCV(lines=lines, entries=[entry], total_years=5.0)


def _words_cv(words: int, total_years: float | None) -> ParsedCV:
    lines = [
        CVLine(id=f"L{i:03d}", text=" ".join(["word"] * 20)) for i in range(1, words // 20 + 1)
    ]
    return ParsedCV(lines=lines, total_years=total_years)


def test_bullets_without_numbers_get_a_tip():
    cv = _experience_cv(
        [
            "Built data pipelines for the analytics team",
            "Led code reviews and mentoring for new hires",
            "Automated the monthly reporting process",
        ]
    )

    tip = _find(recruiter_tips(cv), "tip_bullets_without_numbers")

    assert tip is not None
    assert tip.severity == "info"
    assert tip.line_ids == ["L003", "L004", "L005"]


def test_numbered_bullets_get_no_tip():
    cv = _experience_cv(
        [
            "Built 4 data pipelines for the analytics team",
            "Cut report time by 40% with automation",
            "Led 3 code reviews every week",
        ]
    )

    assert "tip_bullets_without_numbers" not in _codes(recruiter_tips(cv))


def test_short_cv_gets_a_word_count_tip():
    assert "tip_word_count" in _codes(recruiter_tips(_words_cv(120, None)))


def test_normal_length_gets_no_word_count_tip():
    assert "tip_word_count" not in _codes(recruiter_tips(_words_cv(400, 5.0)))


def test_long_cv_with_few_years_gets_a_word_count_tip():
    tip = _find(recruiter_tips(_words_cv(1000, 5.0)), "tip_word_count")

    assert tip is not None
    assert "1000 words" in tip.message


def test_long_cv_is_fine_for_senior_or_unknown_experience():
    assert "tip_word_count" not in _codes(recruiter_tips(_words_cv(1000, 12.0)))
    assert "tip_word_count" not in _codes(recruiter_tips(_words_cv(1000, None)))


def test_line_over_40_words_gets_a_paragraph_tip():
    cv = ParsedCV(lines=[CVLine(id="L001", text=" ".join(["word"] * 45))])

    tip = _find(recruiter_tips(cv), "tip_long_paragraph")

    assert tip is not None
    assert tip.line_ids == ["L001"]


def test_line_of_40_words_gets_no_paragraph_tip():
    cv = ParsedCV(lines=[CVLine(id="L001", text=" ".join(["word"] * 40))])

    assert "tip_long_paragraph" not in _codes(recruiter_tips(cv))
