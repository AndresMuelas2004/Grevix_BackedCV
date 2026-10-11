import pytest

from backedcv.domain.document_diff import (
    apply_suggestions,
    diff_document,
    document_from_cv,
    move_section,
    reorder_items,
    validate_document,
)
from backedcv.domain.models import (
    Contact,
    ContactField,
    CVDocument,
    CVEntry,
    CVLine,
    CVSection,
    DocLine,
    ParsedCV,
    Suggestion,
    Verification,
)

TEXTS = [
    ("L001", "Jane Doe"),
    ("L002", "jane@example.com | +34 600 123 456"),
    ("L003", "Madrid, Spain"),
    ("L004", "linkedin.com/in/janedoe"),
    ("L005", "Summary"),
    ("L006", "Backend engineer with 5 years of Python APIs."),
    ("L007", "Experience"),
    ("L008", "Senior Engineer"),
    ("L009", "Acme Corp, 2021-03 - Present"),
    ("L010", "Built the billing API in Python"),
    ("L011", "Led a team of four engineers"),
    ("L012", "Junior Developer"),
    ("L013", "Beta Labs, 2018-06 - 2020-12"),
    ("L014", "Wrote the first ETL pipeline"),
    ("L015", "Skills"),
    ("L016", "Python, SQL, Docker"),
]


def _cv() -> ParsedCV:
    """Contact, summary, experience with two jobs, and skills."""
    return ParsedCV(
        lines=[CVLine(id=line_id, text=text) for line_id, text in TEXTS],
        contact=Contact(
            name=ContactField(value="Jane Doe", line_id="L001"),
            email=ContactField(value="jane@example.com", line_id="L002"),
            phone=ContactField(value="+34 600 123 456", line_id="L002"),
            location=ContactField(value="Madrid, Spain", line_id="L003"),
            links=[ContactField(value="linkedin.com/in/janedoe", line_id="L004")],
        ),
        sections=[
            CVSection(
                id="S00",
                heading_line_id=None,
                type="contact",
                line_ids=["L001", "L002", "L003", "L004"],
            ),
            CVSection(id="S01", heading_line_id="L005", type="summary", line_ids=["L005", "L006"]),
            CVSection(
                id="S02",
                heading_line_id="L007",
                type="experience",
                line_ids=["L007", "L008", "L009", "L010", "L011", "L012", "L013", "L014"],
            ),
            CVSection(id="S03", heading_line_id="L015", type="skills", line_ids=["L015", "L016"]),
        ],
        entries=[
            CVEntry(
                id="E01",
                section_id="S02",
                kind="job",
                title="Senior Engineer",
                organization="Acme Corp",
                start="2021-03",
                end="present",
                date_source="parser",
                line_ids=["L008", "L009", "L010", "L011"],
            ),
            CVEntry(
                id="E02",
                section_id="S02",
                kind="job",
                title="Junior Developer",
                organization="Beta Labs",
                start="2018-06",
                end="2020-12",
                date_source="parser",
                line_ids=["L012", "L013", "L014"],
            ),
        ],
    )


def _suggestion(
    sid: str,
    kind: str,
    target: str,
    after: str,
    status: str = "verified",
    before: str | None = None,
) -> Suggestion:
    return Suggestion(
        id=sid,
        kind=kind,
        target=target,
        before=before,
        after=after,
        verification=Verification(status=status),
    )


def _lines(doc: CVDocument) -> list[DocLine]:
    return [line for section in doc.sections for item in section.items for line in item.lines]


def _origins(doc: CVDocument) -> list[str]:
    return [line.origin for line in _lines(doc)]


def _line(doc: CVDocument, origin: str) -> DocLine:
    return next(line for line in _lines(doc) if line.origin == origin)


def test_contact_comes_from_the_cv_and_the_contact_section_is_skipped():
    doc = document_from_cv(_cv())

    assert doc.contact.name == "Jane Doe"
    assert doc.contact.details == [
        "jane@example.com",
        "+34 600 123 456",
        "Madrid, Spain",
        "linkedin.com/in/janedoe",
    ]
    assert doc.contact.origins == ["L001", "L002", "L003", "L004"]
    assert [section.id for section in doc.sections] == ["S01", "S02", "S03"]


def test_entries_become_items_and_only_title_organization_and_date_lines_are_text():
    doc = document_from_cv(_cv())

    experience = doc.sections[1]
    assert (experience.heading, experience.heading_origin) == ("Experience", "L007")
    assert [item.id for item in experience.items] == ["E01", "E02"]
    kinds = [(line.origin, line.kind) for item in experience.items for line in item.lines]
    assert kinds == [
        ("L008", "text"),
        ("L009", "text"),
        ("L010", "bullet"),
        ("L011", "bullet"),
        ("L012", "text"),
        ("L013", "text"),
        ("L014", "bullet"),
    ]


def test_loose_lines_are_grouped_and_every_body_line_appears_once():
    cv = _cv()
    doc = document_from_cv(cv)

    summary, skills = doc.sections[0], doc.sections[2]
    assert (summary.heading, summary.heading_origin) == ("Summary", "L005")
    assert [(item.id, item.lines[0].kind) for item in summary.items] == [("S01-i1", "text")]
    assert [item.id for item in skills.items] == ["S03-i1"]
    assert _origins(doc) == [
        "L006",
        "L008",
        "L009",
        "L010",
        "L011",
        "L012",
        "L013",
        "L014",
        "L016",
    ]
    assert validate_document(doc, cv, [], []) == []


def test_missing_heading_gets_a_standard_one_and_lines_outside_sections_are_kept():
    cv = ParsedCV(
        lines=[
            CVLine(id="L001", text="Ana Ruiz"),
            CVLine(id="L002", text="English (C1)"),
            CVLine(id="L003", text="Spanish (native)"),
            CVLine(id="L004", text="Available from May"),
        ],
        contact=Contact(name=ContactField(value="Ana Ruiz", line_id="L001")),
        sections=[
            CVSection(id="S01", heading_line_id=None, type="languages", line_ids=["L002", "L003"])
        ],
    )

    doc = document_from_cv(cv)

    assert [(s.heading, s.heading_origin) for s in doc.sections] == [
        ("Languages", None),
        ("Other", None),
    ]
    assert _origins(doc) == ["L002", "L003", "L004"]
    assert validate_document(doc, cv, [], []) == []


def test_apply_each_kind_of_suggestion():
    cv = _cv()
    doc = document_from_cv(cv)
    suggestions = [
        _suggestion(
            "S01",
            "align_wording",
            "L011",
            "Led a team of four engineers across two squads",
            before="Led a team of four engineers",
        ),
        _suggestion("S02", "tailor_summary", "S01", "Python backend engineer focused on APIs."),
        _suggestion("S03", "add_skill", "S03", "FastAPI"),
    ]

    applied = apply_suggestions(doc, cv, suggestions, ["S01", "S02", "S03"])

    assert _origins(applied) == [
        "S02",
        "L008",
        "L009",
        "L010",
        "S01",
        "L012",
        "L013",
        "L014",
        "L016",
        "S03",
    ]
    assert _line(applied, "S01").text == "Led a team of four engineers across two squads"
    assert _line(applied, "S01").kind == "bullet"
    assert _line(applied, "S03").kind == "text"
    assert [item.id for item in applied.sections[0].items] == ["S01-i1"]
    assert validate_document(applied, cv, suggestions, ["S01", "S02", "S03"]) == []


def test_missing_targets_create_added_sections_once():
    cv = _cv()
    doc = document_from_cv(cv)
    suggestions = [
        _suggestion("S07", "add_skill", "S09", "Kubernetes"),
        _suggestion("S08", "tailor_summary", "new-summary", "Backend engineer focused on APIs."),
    ]

    applied = apply_suggestions(doc, cv, suggestions, ["S07", "S08"])

    assert [section.id for section in applied.sections] == [
        "added-summary",
        "S01",
        "S02",
        "S03",
        "added-skills",
    ]
    added_summary, added_skills = applied.sections[0], applied.sections[-1]
    assert (added_summary.type, added_summary.heading) == ("summary", "Summary")
    assert (added_skills.type, added_skills.heading) == ("skills", "Skills")
    assert _origins(applied)[0] == "S08"
    assert _origins(applied)[-1] == "S07"
    assert validate_document(applied, cv, suggestions, ["S07", "S08"]) == []


def test_unverified_or_unaccepted_suggestions_are_not_applied():
    cv = _cv()
    doc = document_from_cv(cv)
    unsupported = _suggestion(
        "S05", "align_wording", "L014", "Wrote the first ETL pipeline in Airflow", "unsupported"
    )
    not_accepted = _suggestion("S06", "add_skill", "S03", "Kubernetes")

    applied = apply_suggestions(doc, cv, [unsupported, not_accepted], ["S05"])

    assert applied == doc


def test_apply_does_not_change_its_inputs():
    cv = _cv()
    doc = document_from_cv(cv)
    before = doc.model_dump()

    apply_suggestions(doc, cv, [_suggestion("S03", "add_skill", "S03", "FastAPI")], ["S03"])

    assert doc.model_dump() == before


def test_validator_catches_a_tampered_line():
    cv = _cv()
    tampered = document_from_cv(cv).model_copy(deep=True)
    _line(tampered, "L014").text = "Wrote the first ETL pipeline in Spark"

    errors = validate_document(tampered, cv, [], [])

    assert len(errors) == 1
    assert "L014" in errors[0]


def test_validator_catches_a_lost_line():
    cv = _cv()
    lost = document_from_cv(cv).model_copy(deep=True)
    beta_labs = lost.sections[1].items[1]
    beta_labs.lines = [line for line in beta_labs.lines if line.origin != "L014"]

    assert validate_document(lost, cv, [], []) == [
        "Original line L014 is missing from the document"
    ]


def test_validator_rejects_lines_from_suggestions_that_are_not_accepted():
    cv = _cv()
    suggestions = [_suggestion("S03", "add_skill", "S03", "FastAPI")]
    doc = apply_suggestions(document_from_cv(cv), cv, suggestions, ["S03"])

    errors = validate_document(doc, cv, suggestions, [])

    assert any("S03" in error for error in errors)


def test_validator_catches_repeated_section_ids():
    cv = _cv()
    doc = document_from_cv(cv).model_copy(deep=True)
    doc.sections.append(doc.sections[0].model_copy(deep=True))

    assert "Section ID S01 appears 2 times" in validate_document(doc, cv, [], [])


def test_diff_marks_changed_added_and_removed_lines():
    cv = _cv()
    suggestions = [
        _suggestion(
            "S01",
            "align_wording",
            "L011",
            "Led a team of four engineers across two squads",
            before="Led a team of four engineers",
        ),
        _suggestion("S02", "tailor_summary", "S01", "Python backend engineer focused on APIs."),
        _suggestion("S03", "add_skill", "S03", "FastAPI"),
    ]
    doc = apply_suggestions(document_from_cv(cv), cv, suggestions, ["S01", "S02", "S03"])

    diff = diff_document(cv, doc, suggestions)

    assert [entry.status for entry in diff] == [
        "removed",
        "added",
        "unchanged",
        "unchanged",
        "unchanged",
        "changed",
        "unchanged",
        "unchanged",
        "unchanged",
        "unchanged",
        "added",
    ]
    removed, changed = diff[0], diff[5]
    assert (removed.section_id, removed.origin) == ("S01", "L006")
    assert removed.before == "Backend engineer with 5 years of Python APIs."
    assert (changed.section_id, changed.origin) == ("S02", "S01")
    assert changed.before == "Led a team of four engineers"
    assert changed.after == "Led a team of four engineers across two squads"


def test_diff_of_the_original_document_is_all_unchanged():
    cv = _cv()

    diff = diff_document(cv, document_from_cv(cv))

    assert {entry.status for entry in diff} == {"unchanged"}
    assert len(diff) == 9


def test_move_section_returns_a_new_document():
    doc = document_from_cv(_cv())

    moved = move_section(doc, "S03", 0)

    assert [section.id for section in moved.sections] == ["S03", "S01", "S02"]
    assert [section.id for section in doc.sections] == ["S01", "S02", "S03"]


def test_reorder_items_returns_a_new_document():
    doc = document_from_cv(_cv())

    reordered = reorder_items(doc, "S02", ["E02", "E01"])

    assert [item.id for item in reordered.sections[1].items] == ["E02", "E01"]
    assert [item.id for item in doc.sections[1].items] == ["E01", "E02"]


def test_move_and_reorder_reject_unknown_ids_and_bad_orders():
    doc = document_from_cv(_cv())

    with pytest.raises(ValueError, match="Unknown section"):
        move_section(doc, "S99", 0)
    with pytest.raises(ValueError, match="out of range"):
        move_section(doc, "S01", 3)
    with pytest.raises(ValueError, match="Unknown section"):
        reorder_items(doc, "S99", ["E01"])
    with pytest.raises(ValueError, match="missing"):
        reorder_items(doc, "S02", ["E01"])
    with pytest.raises(ValueError, match="E09"):
        reorder_items(doc, "S02", ["E01", "E09"])
    with pytest.raises(ValueError, match="exactly once"):
        reorder_items(doc, "S02", ["E01", "E01"])
