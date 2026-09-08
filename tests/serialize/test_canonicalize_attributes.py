from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from turbohtml import Element


@pytest.mark.parametrize("size", [1, 31, 32, 33, 1_000], ids=["single", "31-attrs", "32-attrs", "33-attrs", "wide"])
def test_canonicalize_orders_many_attributes(size: int) -> None:
    element: Final[Element] = parse(
        "<div " + " ".join(f'data-{index:05d}="{index}"' for index in range(size, 0, -1)) + "></div>"
    ).select("div")[0]
    assert (
        element.canonicalize()
        == ("<div " + " ".join(f'data-{index:05d}="{index}"' for index in range(1, size + 1)) + "></div>").encode()
    )
