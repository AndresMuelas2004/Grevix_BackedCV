from datetime import date

import pytest

from backedcv.domain.dates import parse_date_range, total_months, years_from_months

TODAY = date(2026, 10, 11)


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("Data Engineer, Acme | Jan 2020 - Present", "2020-01", "present"),
        ("March 2018 – June 2019", "2018-03", "2019-06"),
        ("03/2019 - 11/2021", "2019-03", "2021-11"),
        ("2019 - 2021", "2019", "2021"),  # only the year: no month is invented
        ("ene. 2022 - actualidad", "2022-01", "present"),
        ("septiembre de 2017 – marzo de 2020", "2017-09", "2020-03"),
        ("2020-05 to 2022-01", "2020-05", "2022-01"),
        ("Since 2021", "2021", "present"),
        ("BSc Computer Science, 2016", "2016", None),
    ],
)
def test_parse_date_range(text, start, end):
    parsed = parse_date_range(text)

    assert parsed is not None
    assert parsed.start.iso() == start
    assert parsed.end_iso() == end


def test_no_date():
    assert parse_date_range("Python, SQL, Docker") is None


def test_total_months_merges_overlaps_and_counts_inclusive_months():
    ranges = [
        parse_date_range("Jan 2020 - Mar 2020"),  # 3 months
        parse_date_range("Feb 2020 - Jun 2020"),  # overlaps: union Jan-Jun = 6
        parse_date_range("2016"),  # single date: not a period
    ]

    assert total_months(ranges, TODAY) == 6


def test_present_counts_the_current_month():
    months = total_months([parse_date_range("Oct 2025 - Present")], TODAY)

    assert months == 13
    assert years_from_months(months) == 1.1
