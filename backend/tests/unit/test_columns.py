from pathlib import Path

import typst

from backedcv.ingestion import read_cv

TWO_COLUMN_CV = """\
#set page(width: 210mm, height: 297mm, margin: 15mm)
#set text(size: 10pt)
= Jane Doe

#grid(
  columns: (1fr, 1fr),
  gutter: 8mm,
  [
    *Experience*

    Data Engineer, Acme Corp, Jan 2020 - Present

    - Built ETL pipelines in Python and SQL for the analytics team
    - Led a team of four analysts through the warehouse migration

    *Education*

    BSc Computer Science, University of Madrid, 2016
  ],
  [
    *Skills*

    Python, SQL, Docker, Airflow and dbt

    *Languages*

    English and Spanish
  ],
)
"""

ONE_COLUMN_CV = """\
#set page(width: 210mm, height: 297mm, margin: 20mm)
= Jane Doe

*Experience*

Data Engineer, Acme Corp

- Built ETL pipelines in Python and SQL for the analytics team across three regions
- Led a team of four analysts through the warehouse migration to the cloud

*Skills*

Python, SQL, Docker
"""

# Dates sit on the right of single-column job lines: that must not look like a second column.
DATES_ON_RIGHT_CV = """\
#set page(width: 210mm, height: 297mm, margin: 20mm)
= Jane Doe

*Experience*

Data Engineer, Acme Corp #h(1fr) 2020 - Present

Data Analyst, Beta Inc #h(1fr) 2017 - 2020

Intern, Gamma Ltd #h(1fr) 2016 - 2017

*Education*

BSc Computer Science #h(1fr) 2016
"""

# Short one-line items with three long lines between them, reaching past the middle of the page.
SHORT_AND_LONG_LINES_CV = """\
#set page(width: 210mm, height: 297mm, margin: 20mm)
#set text(size: 10.5pt)
= Jane Doe

Python

SQL

Built ETL pipelines in Python and SQL that cut monthly reporting time
by forty percent for the finance team

Docker

Git

Airflow

dbt

Spark

Team lead

Data Engineer, Acme

Led a team of four analysts through the warehouse migration to the cloud platform every quarter

Analyst, Beta

Intern, Gamma

Teaching

Mentoring

Reporting

Automated the data quality checks for every nightly load across all
regional warehouses and dashboards

Dashboards

Testing

Linux

Terraform
"""

SAMPLE_CV = Path(__file__).resolve().parents[2] / "samples" / "curated" / "cv.pdf"


def _pdf(tmp_path, markup: str) -> bytes:
    source = tmp_path / "cv.typ"
    source.write_text(markup, encoding="utf-8")
    return typst.compile(str(source))


def _positions(texts: list[str], keys: list[str]) -> list[int]:
    """Index of the line that contains each key, in the order the keys are given."""
    return [next(i for i, text in enumerate(texts) if key in text) for key in keys]


def test_two_column_cv_is_read_column_by_column(tmp_path):
    result = read_cv(_pdf(tmp_path, TWO_COLUMN_CV), "cv.pdf")
    texts = [line.text for line in result.lines]
    keys = [
        "Experience",
        "Data Engineer",
        "Built ETL",
        "Led a team",
        "Education",
        "BSc Computer",
        "Skills",
        "Python, SQL, Docker",
        "Languages",
        "English and Spanish",
    ]

    assert result.multi_column
    assert texts[0] == "Jane Doe"
    positions = _positions(texts, keys)
    assert positions == sorted(positions)


def test_one_column_cv_keeps_its_order(tmp_path):
    result = read_cv(_pdf(tmp_path, ONE_COLUMN_CV), "cv.pdf")
    texts = [line.text for line in result.lines]
    keys = [
        "Jane Doe",
        "Experience",
        "Data Engineer",
        "Built ETL",
        "Led a team",
        "Skills",
        "Python, SQL, Docker",
    ]

    assert not result.multi_column
    positions = _positions(texts, keys)
    assert positions == sorted(positions)


def test_dates_on_the_right_do_not_make_two_columns(tmp_path):
    result = read_cv(_pdf(tmp_path, DATES_ON_RIGHT_CV), "cv.pdf")
    texts = [line.text for line in result.lines]
    keys = [
        "Experience",
        "Data Engineer",
        "Data Analyst",
        "Intern",
        "Education",
        "BSc Computer",
    ]

    assert not result.multi_column
    positions = _positions(texts, keys)
    assert positions == sorted(positions)


def test_short_lines_with_a_few_long_lines_stay_one_column(tmp_path):
    result = read_cv(_pdf(tmp_path, SHORT_AND_LONG_LINES_CV), "cv.pdf")
    texts = [line.text for line in result.lines]
    keys = [
        "Python",
        "Built ETL",
        "Docker",
        "Team lead",
        "Led a team",
        "Automated",
        "Terraform",
    ]

    assert not result.multi_column
    positions = _positions(texts, keys)
    assert positions == sorted(positions)


def test_sample_cv_reads_header_then_left_column_then_right_column():
    result = read_cv(SAMPLE_CV.read_bytes(), "cv.pdf")
    texts = [line.text for line in result.lines]
    header = ["Nuria Calvo Ruiz", "Software engineer moving into AI engineering"]
    left = [
        "Contact",
        "Valencia, Spain",
        "nuria.calvo@example.com",
        "Education",
        "Skills",
        "Languages",
    ]
    right = ["Summary", "Software engineer with three years", "Experience", "Projects"]
    left_positions = _positions(texts, left)
    right_positions = _positions(texts, right)

    assert result.multi_column
    assert _positions(texts, header) == [0, 1]
    assert left_positions == sorted(left_positions)
    assert right_positions == sorted(right_positions)
    # Strictly before: a line holding a left item and a right item would give equal positions.
    assert max(left_positions) < min(right_positions)
