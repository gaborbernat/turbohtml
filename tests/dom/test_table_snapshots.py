from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml import parse


@pytest.mark.parametrize(
    "text", [pytest.param("x" * 4096, id="long"), pytest.param("é猫😀", id="wide"), pytest.param("", id="empty")]
)
def test_table_span_snapshot_survives_tree_mutation(text: str) -> None:
    document: Final = parse(f"<table><tr><td rowspan=2 colspan=3> {text} </td></tr><tr></tr></table>")
    table: Final = document.select("table")[0]
    result: Final = table.rows()
    document.select("td")[0].text = "changed"
    assert result == [[text] * 3, [text] * 3]


def test_table_span_rows_are_independent() -> None:
    result: Final = parse("<table><tr><td rowspan=2 colspan=2>x</td></tr><tr></tr></table>").select("table")[0].rows()
    result[0][0] = "changed"
    assert result == [["changed", "x"], ["x", "x"]]


@pytest.mark.parametrize(
    ("case", "columns", "size"),
    [pytest.param(0, 128, 4096, id="large-span"), pytest.param(1, 1, 16, id="ordinary")],
)
def test_table_span_rows_benchmark(case: int, columns: int, size: int) -> None:
    source: Final = cast("tuple[str, str]", INPUTS["tables-spans"]()[case][1])[1]
    assert parse(source).tables() == [[["header"] * columns, ["x" * size] * columns]]


def test_table_span_records_benchmark() -> None:
    source: Final = cast("tuple[str, str]", INPUTS["tables-spans"]()[2][1])[1]
    assert parse(source).select("table")[0].records() == [{"header": "x" * 4096}]
