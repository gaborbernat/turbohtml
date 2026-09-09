from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from turbohtml import Element


@pytest.mark.parametrize(
    "size",
    [
        pytest.param(1, id="single"),
        pytest.param(31, id="31-attrs"),
        pytest.param(32, id="32-attrs"),
        pytest.param(33, id="33-attrs"),
        pytest.param(1_000, id="wide"),
    ],
)
def test_canonicalize_orders_many_attributes(size: int) -> None:
    element: Final[Element] = parse(
        "<div " + " ".join(f'data-{index:05d}="{index}"' for index in range(size, 0, -1)) + "></div>"
    ).select("div")[0]
    assert (
        element.canonicalize()
        == ("<div " + " ".join(f'data-{index:05d}="{index}"' for index in range(1, size + 1)) + "></div>").encode()
    )
