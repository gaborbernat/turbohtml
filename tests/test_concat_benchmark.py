from __future__ import annotations

from typing import cast

import pytest
from bench.ci import benchmarks

from turbohtml import parse


@pytest.mark.parametrize(
    ("name", "length"),
    [
        pytest.param("xpath-concat", 320_000, id="many-short-nodes"),
        pytest.param("xpath-concat-long", 327_680, id="few-long-nodes"),
    ],
)
def test_concat_benchmark_output(name: str, length: int) -> None:
    _, _, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == name)
    expression, source = cast("tuple[str, str]", load())
    assert parse(source).xpath(expression) == "a" * length
