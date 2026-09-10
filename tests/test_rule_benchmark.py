from __future__ import annotations

from typing import Final, cast

import pytest
from bench.ci import benchmarks


@pytest.mark.parametrize("library", ["core", "competitors.lxml"], ids=["turbohtml", "lxml"])
@pytest.mark.parametrize(
    ("name", "passes"),
    [pytest.param("transform-rules", 8, id="repeated"), pytest.param("transform-rules-single", 1, id="single")],
)
def test_rule_benchmark_output(library: str, name: str, passes: int) -> None:
    module: Final = pytest.importorskip(f"bench.{library}", exc_type=ImportError)
    operation: Final = module.OPERATIONS["transform-rules"][0]
    _, _, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == name)
    expected: Final = "".join(f"{ordinal}|" for ordinal in range(1, 1_025)) * passes
    assert str(operation(cast("tuple[str, str]", load()))) == expected
