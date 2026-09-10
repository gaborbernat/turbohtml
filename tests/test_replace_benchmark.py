from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from bench.ci import benchmarks
from bench.core import OPERATIONS

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize("name", ["xpath-replace", "xpath-replace-short"])
def test_replace_benchmark_output(name: str) -> None:
    _, _, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == name)
    case = cast("tuple[str, str, str, str]", load())
    operation = cast("Callable[[tuple[str, str, str, str]], str]", OPERATIONS["xpath-replace"][0])
    assert operation(case) == case[3]
