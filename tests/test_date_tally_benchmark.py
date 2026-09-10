from __future__ import annotations

from typing import cast

import pytest
from bench.ci import benchmarks

from turbohtml.extract import PublicationDate, dates


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("date-tally", "2002-09-26", id="distinct"),
        pytest.param("date-tally-repeated", "2000-01-01", id="repeated"),
    ],
)
def test_date_tally_benchmark_output(name: str, expected: str) -> None:
    _, _, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == name)
    assert dates(cast("str", load())) == PublicationDate(expected, "text")
