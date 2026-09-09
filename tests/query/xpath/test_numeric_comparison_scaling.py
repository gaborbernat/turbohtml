from __future__ import annotations

from operator import ge, gt, le, lt
from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("left", "right"),
    [
        pytest.param(("2",) * 32, ("1",) * 32, id="descending"),
        pytest.param(("1",) * 32, ("2",) * 32, id="ascending"),
        pytest.param(("2",) * 32, ("2",) * 32, id="equal"),
        pytest.param(("2",) * 31 + ("0",), ("1",) * 32, id="late-left-minimum"),
        pytest.param(("1",) * 31 + ("3",), ("2",) * 32, id="late-left-maximum"),
        pytest.param(("2",) * 32, ("1",) * 31 + ("3",), id="late-right-maximum"),
        pytest.param(("1",) * 32, ("2",) * 31 + ("0",), id="late-right-minimum"),
        pytest.param(("NaN",) * 32, ("1",) * 32, id="left-nan"),
        pytest.param(("1",) * 32, ("NaN",) * 32, id="right-nan"),
        pytest.param(("NaN", "1") * 16, ("NaN", "2") * 16, id="nan-and-numbers"),
        pytest.param(("1", "NaN") * 16, ("2", "NaN") * 16, id="numbers-and-nan"),
        pytest.param(("-0",) * 16, ("0",) * 16, id="signed-zero"),
        pytest.param(("2",) * 15, ("1",) * 16, id="small-left"),
        pytest.param(("2",) * 16, ("1",) * 15, id="small-right"),
    ],
)
@pytest.mark.parametrize(
    ("operation", "compare"),
    [
        pytest.param("<", lt, id="lt"),
        pytest.param("<=", le, id="le"),
        pytest.param(">", gt, id="gt"),
        pytest.param(">=", ge, id="ge"),
    ],
)
def test_numeric_node_set_comparison(
    left: tuple[str, ...], right: tuple[str, ...], operation: str, compare: Callable[[float, float], bool]
) -> None:
    document: Final = parse_xml(
        "<root>"
        + "".join(f"<left>{value}</left>" for value in left)
        + "".join(f"<right>{value}</right>" for value in right)
        + "</root>"
    )
    assert document.xpath(f"//left {operation} //right") is any(
        compare(float(first), float(second)) for first in left for second in right
    )
