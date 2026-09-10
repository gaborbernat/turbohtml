from __future__ import annotations

from datetime import date, timedelta
from typing import Final

import pytest

from turbohtml.extract import DateExtraction, PublicationDate, dates


@pytest.mark.parametrize("count", [1, 17, 1000], ids=["single", "growth", "collisions"])
@pytest.mark.parametrize("original", [True, False], ids=["published", "modified"])
def test_date_tally_ties(count: int, *, original: bool) -> None:
    start: Final = date(2000, 1, 1)
    source: Final = "<p>" + " ".join((start + timedelta(days=index)).isoformat() for index in range(count)) + "</p>"
    expected: Final = start if original else start + timedelta(days=count - 1)
    assert dates(source, DateExtraction(original=original)) == PublicationDate(expected.isoformat(), "text")


@pytest.mark.parametrize("original", [True, False], ids=["published", "modified"])
def test_date_tally_frequency_precedes_date_order(*, original: bool) -> None:
    start: Final = date(2000, 1, 1)
    source: Final = (
        "<p>"
        + " ".join((start + timedelta(days=index)).isoformat() for index in range(100))
        + " 2000-02-01 2000-02-01</p>"
    )
    assert dates(source, DateExtraction(original=original)) == PublicationDate("2000-02-01", "text")


def test_date_tally_repeated_date() -> None:
    assert dates("<p>" + "2000-01-01 " * 1000 + "</p>") == PublicationDate("2000-01-01", "text")
