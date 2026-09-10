from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest
from bench.ci import benchmarks
from bench.operations import INPUTS

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize("library", ["core", "competitors.lxml"], ids=["turbohtml", "lxml"])
@pytest.mark.parametrize(
    ("case", "rows", "instructions", "step"),
    [
        pytest.param(0, 200, 1, 1, id="single-200"),
        pytest.param(1, 200, 8, 1, id="repeated-200"),
        pytest.param(2, 2_000, 1, 1, id="single-2000"),
        pytest.param(3, 2_000, 8, 1, id="repeated-2000"),
        pytest.param(4, 1, 8, 1, id="one-node"),
        pytest.param(5, 200, 8, -1, id="reverse"),
        pytest.param(6, 200, 0, 1, id="no-number"),
    ],
)
def test_number_benchmark_output(library: str, case: int, rows: int, instructions: int, step: int) -> None:
    module: Final = pytest.importorskip(f"bench.{library}", exc_type=ImportError)
    operation: Final = module.OPERATIONS["transform-number"][0]
    positions: Final = range(1, rows + 1) if step == 1 else range(rows, 0, -1)
    expected: Final = "".join(f"{position}:" * instructions + "|" for position in positions)
    assert str(operation(cast("tuple[str, str]", INPUTS["transform-number"]()[case][1]))) == expected


@pytest.mark.parametrize(
    ("name", "instructions"),
    [
        pytest.param("transform-number", 8, id="repeated"),
        pytest.param("transform-number-single", 1, id="single"),
    ],
)
def test_codspeed_number_benchmark_output(name: str, instructions: int) -> None:
    _, operation, load = next(case for case in benchmarks() if case[0] == name)
    expected: Final = "".join(f"{position}:" * instructions + "|" for position in range(1, 2_001))
    assert cast("Callable[[tuple[str, str]], str]", operation)(cast("tuple[str, str]", load())) == expected


@pytest.mark.parametrize("library", ["core", "competitors.lxml"], ids=["turbohtml", "lxml"])
def test_dense_number_benchmark_output(library: str) -> None:
    module: Final = pytest.importorskip(f"bench.{library}", exc_type=ImportError)
    operation: Final = module.OPERATIONS["transform-dense"][0]
    expected: Final = (
        '<?xml version="1.0"?>\n<out>'
        + "".join(
            f"<row>Book number {index}"
            + "".join(f"{index + 1}<!--c{unit}--><title>Book number {index}</title>" for unit in range(8))
            + "</row>"
            for index in range(200)
        )
        + "</out>"
    )
    assert str(operation(cast("tuple[str, str]", INPUTS["transform-dense"]()[0][1]))).strip() == expected
