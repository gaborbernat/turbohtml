from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest
from bench.ci import benchmarks
from bench.core import OPERATIONS
from bench.operations import INPUTS

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize("library", ["core", "competitors.beautifulsoup4"], ids=["turbohtml", "beautifulsoup"])
@pytest.mark.parametrize(
    ("case", "expected"),
    [
        pytest.param(0, True, id="one"),
        pytest.param(1, True, id="ten"),
        pytest.param(2, True, id="below-index"),
        pytest.param(3, True, id="index"),
        pytest.param(4, True, id="hundred"),
        pytest.param(5, True, id="thousand"),
        pytest.param(6, True, id="reversed-hundred"),
        pytest.param(7, True, id="reversed-thousand"),
        pytest.param(8, False, id="early-value"),
        pytest.param(9, False, id="late-value"),
        pytest.param(10, False, id="missing-name"),
        pytest.param(11, True, id="rotated"),
    ],
)
def test_node_equality_benchmark_result(library: str, case: int, *, expected: bool) -> None:
    module: Final = pytest.importorskip(f"bench.{library}", exc_type=ImportError)
    operation: Final = cast("Callable[[tuple[int, str]], bool]", module.OPERATIONS["node-equals"][0])
    assert operation(cast("tuple[int, str]", INPUTS["node-equals"]()[case][1])) is expected


def test_node_equality_duplicate_benchmark_result() -> None:
    operation: Final = cast("Callable[[tuple[int, str]], bool]", OPERATIONS["node-equals"][0])
    assert operation(cast("tuple[int, str]", INPUTS["node-equals"]()[12][1]))


def test_competitor_node_equality_duplicates_unsupported() -> None:
    module: Final = pytest.importorskip("bench.competitors.beautifulsoup4", exc_type=ImportError)
    operation: Final = cast("Callable[[tuple[int, str]], bool]", module.OPERATIONS["node-equals"][0])
    with pytest.raises(ValueError, match="constructor does not normalize case variants"):
        operation(cast("tuple[int, str]", INPUTS["node-equals"]()[12][1]))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("node-equals", True, id="aligned"),
        pytest.param("node-equals-reversed", True, id="reversed"),
        pytest.param("node-equals-early-mismatch", False, id="early-mismatch"),
        pytest.param("node-equals-duplicates", True, id="duplicates"),
    ],
)
def test_codspeed_node_equality_result(name: str, *, expected: bool) -> None:
    _, operation, load = next(case for case in benchmarks() if case[0] == name)
    assert cast("Callable[[object], bool]", operation)(load()) is expected
