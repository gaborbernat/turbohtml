"""EXSLT ``date:`` field-extraction functions built into the XPath engine.

``date:year``, ``date:month-in-year``, ``date:day-in-month``, ``date:day-in-week``,
and ``date:leap-year`` read an explicit ISO 8601 ``YYYY-MM-DD`` string argument (the
implicit "current date-time" form of libexslt is not supported, so the engine stays
deterministic). A string that is not a valid date yields ``NaN`` (or ``False`` for
``date:leap-year``).
"""

from __future__ import annotations

import math

import pytest

import turbohtml


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse("<p>x</p>")


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("date:year('2024-06-22')", 2024.0, id="year"),
        pytest.param("date:month-in-year('2024-06-22')", 6.0, id="month"),
        pytest.param("date:day-in-month('2024-06-22')", 22.0, id="day"),
        pytest.param("date:day-in-week('2024-06-22')", 7.0, id="day-in-week-saturday"),
        pytest.param("date:day-in-week('2024-01-15')", 2.0, id="day-in-week-monday-pre-march"),
        pytest.param("date:year('2024-06-22T10:30:00')", 2024.0, id="year-with-time-t"),
        pytest.param("date:year('2024-06-22 10:30:00')", 2024.0, id="year-with-time-space"),
    ],
)
def test_date_numbers(doc: turbohtml.Node, expr: str, expected: float) -> None:
    assert doc.xpath(expr) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expr",
    [
        pytest.param("date:year('not-a-date')", id="non-numeric"),
        pytest.param("date:year('2024-06')", id="too-short"),
        pytest.param("date:year('2024/06/22')", id="wrong-first-separator"),
        pytest.param("date:year('2024-06.22')", id="wrong-second-separator"),
        pytest.param("date:year('XXXX-06-22')", id="bad-year-digits"),
        pytest.param("date:year('2024-XX-22')", id="bad-month-digits-above-nine"),
        pytest.param("date:year('202/-06-22')", id="bad-year-digit-below-zero"),
        pytest.param("date:year('2024-06-XX')", id="bad-day-digits"),
        pytest.param("date:year('2024-13-01')", id="month-too-large"),
        pytest.param("date:year('2024-00-01')", id="month-too-small"),
        pytest.param("date:year('2024-06-32')", id="day-too-large"),
        pytest.param("date:year('2024-06-00')", id="day-too-small"),
        pytest.param("date:year('2024-06-22Z')", id="trailing-junk"),
    ],
)
def test_date_invalid_is_nan(doc: turbohtml.Node, expr: str) -> None:
    result = doc.xpath(expr)
    assert isinstance(result, float)
    assert math.isnan(result)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("date:leap-year('2024-01-01')", True, id="divisible-by-four"),
        pytest.param("date:leap-year('2023-01-01')", False, id="not-divisible-by-four"),
        pytest.param("date:leap-year('2000-01-01')", True, id="divisible-by-four-hundred"),
        pytest.param("date:leap-year('1900-01-01')", False, id="century-not-leap"),
        pytest.param("date:leap-year('bad')", False, id="invalid-is-false"),
    ],
)
def test_date_leap_year(doc: turbohtml.Node, expr: str, *, expected: bool) -> None:
    assert doc.xpath(expr) is expected
