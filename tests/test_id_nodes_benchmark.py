from __future__ import annotations

from typing import cast

import pytest
from bench.ci import benchmarks

from turbohtml import parse


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("xpath-id-nodes", id="many-short-nodes"),
        pytest.param("xpath-id-nodes-long", id="few-long-nodes"),
    ],
)
def test_id_nodes_benchmark_output(name: str) -> None:
    _, _, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == name)
    expression, source = cast("tuple[str, str]", load())
    assert parse(source).xpath(expression) == ["first", "second"]
