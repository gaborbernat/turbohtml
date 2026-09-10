from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest
from bench import core
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
    ("name", "instructions", "rows", "step"),
    [
        pytest.param("transform-number", 8, 2_000, 1, id="repeated"),
        pytest.param("transform-number-single", 1, 2_000, 1, id="single"),
        pytest.param("transform-number-any", 1, 1_024, 1, id="any-forward"),
        pytest.param("transform-number-any-reversed", 1, 1_024, -1, id="any-reverse"),
        pytest.param("transform-number-count", 1, 1_024, 1, id="any-count"),
    ],
)
def test_codspeed_number_benchmark_output(name: str, instructions: int, rows: int, step: int) -> None:
    _, operation, load = next(case for case in benchmarks() if case[0] == name)
    positions: Final = range(1, rows + 1) if step == 1 else range(rows, 0, -1)
    expected: Final = "".join(f"{position}:" * instructions + "|" for position in positions)
    assert cast("Callable[[tuple[str, str]], str]", operation)(cast("tuple[str, str]", load())) == expected


@pytest.mark.parametrize("library", ["core", "competitors.lxml"], ids=["turbohtml", "lxml"])
@pytest.mark.parametrize(
    ("case", "expected"),
    [
        pytest.param(7, "".join(f"{ordinal}:|" for ordinal in range(1, 33)), id="any-small"),
        pytest.param(8, "".join(f"{ordinal}:|" for ordinal in range(1, 1_025)), id="any-forward"),
        pytest.param(9, "".join(f"{ordinal}:|" for ordinal in range(1_024, 0, -1)), id="any-reverse"),
        pytest.param(10, "1024:|", id="any-last-only"),
        pytest.param(11, "".join(f"{ordinal}:|" * 2 for ordinal in range(1, 513)), id="any-alternating"),
        pytest.param(12, "".join(f"{ordinal}:|" for ordinal in range(1, 1_025)), id="any-mixed-nodes"),
        pytest.param(13, "1:" * 8 + "|", id="any-repeated"),
        pytest.param(14, "".join(f"{ordinal}:|" for ordinal in range(1, 1_025)), id="any-explicit-count"),
        pytest.param(15, "1:|2:|", id="any-two-nodes"),
        pytest.param(16, "".join(f"{ordinal}:|" for ordinal in range(1, 9)), id="any-eight-nodes"),
        pytest.param(17, "1:|", id="count-single-call"),
        pytest.param(18, "1:|", id="predicate-single-call"),
        pytest.param(19, "1:|", id="union-single-call"),
        pytest.param(20, "".join(f"{ordinal}:|" for ordinal in range(1, 1_025)), id="count-predicate"),
        pytest.param(22, "".join(f"{ordinal}:|" for ordinal in range(1, 65)) * 16, id="count-from-sections"),
        pytest.param(23, "".join(f"{ordinal}:|" for ordinal in range(1_024, 0, -1)), id="count-reverse"),
        pytest.param(24, "".join(f"{ordinal}:" * 8 + "|" for ordinal in range(1, 1_025)), id="count-repeated"),
        pytest.param(25, "".join(f"{ordinal}:|" for ordinal in range(2, 1_026)), id="count-wildcard"),
        pytest.param(26, "0:|" * 1_024, id="count-empty"),
    ],
)
def test_any_number_benchmark_output(library: str, case: int, expected: str) -> None:
    module: Final = pytest.importorskip(f"bench.{library}", exc_type=ImportError)
    operation: Final = module.OPERATIONS["transform-number"][0]
    assert str(operation(cast("tuple[str, str]", INPUTS["transform-number"]()[case][1]))) == expected


def test_number_benchmark_current_pattern() -> None:
    expected: Final = "".join(f"{ordinal}:|" * 2 for ordinal in range(1, 513))
    assert core.transform(cast("tuple[str, str]", INPUTS["transform-number"]()[21][1])) == expected


def test_codspeed_number_from_benchmark_output() -> None:
    _, operation, load = next(case for case in benchmarks() if case[0] == "transform-number-count-from")
    expected: Final = "".join(f"{ordinal}:|" for ordinal in range(1, 65)) * 16
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
