from __future__ import annotations

import io
from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml import parse

_PANDAS: Final = pytest.importorskip("pandas")


@pytest.mark.parametrize(
    ("case", "columns", "size"),
    [pytest.param(0, 128, 4096, id="large-span"), pytest.param(1, 1, 16, id="ordinary")],
)
def test_table_span_header_rows_differ(case: int, columns: int, size: int) -> None:
    source: Final = cast("tuple[str, str]", INPUTS["tables-spans"]()[case][1])[1]
    assert (
        parse(source).tables(),
        [frame.to_numpy().tolist() for frame in _PANDAS.read_html(io.StringIO(source))],
    ) == (
        [[["header"] * columns, ["x" * size] * columns]],
        [[["x" * size] * columns]],
    )


def test_table_span_duplicate_headers_differ() -> None:
    source: Final = cast("tuple[str, str]", INPUTS["tables-spans"]()[2][1])[1]
    assert (
        parse(source).select("table")[0].records(),
        _PANDAS.read_html(io.StringIO(source), header=0)[0].to_dict("records"),
    ) == (
        [{"header": "x" * 4096}],
        [{"header" if index == 0 else f"header.{index}": "x" * 4096 for index in range(128)}],
    )
