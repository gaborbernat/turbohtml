from __future__ import annotations

from typing import Final, cast

import pytest
from bench.ci import benchmarks


@pytest.mark.parametrize("library", ["core", "competitors.lxml"], ids=["turbohtml", "lxml"])
@pytest.mark.parametrize(
    "name",
    [
        pytest.param("transform-names", id="many-declarations"),
        pytest.param("transform-names-small", id="small"),
        pytest.param("transform-names-compile", id="compile-source"),
    ],
)
def test_name_benchmark_output(library: str, name: str) -> None:
    module: Final = pytest.importorskip(f"bench.{library}", exc_type=ImportError)
    operation: Final = module.OPERATIONS["transform-names"][0]
    _, _, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == name)
    expected: Final = "<out>" + '<item marker="hit">1</item>' * 256 + "</out>"
    assert str(operation(cast("tuple[str, str]", load()))).strip() == expected
