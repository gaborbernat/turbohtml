from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from types import SimpleNamespace

    from turbohtml import Document, Element


@pytest.mark.parametrize(
    "expression",
    [
        pytest.param("unordered(//li) | //ul", id="left-extension"),
        pytest.param("//ul | unordered(//li)", id="right-extension"),
        pytest.param("unordered(//li) | unordered(//li)", id="both-extensions"),
    ],
)
def test_union_orders_extension_results(expression: str) -> None:
    document: Final[Document] = parse("<ul>" + "".join(f"<li>{index}</li>" for index in range(100)) + "</ul>")
    assert document.xpath(expression, extensions={(None, "unordered"): _unordered}) == document.select(
        "ul, li" if "//ul" in expression else "li"
    )


def _unordered(_context: SimpleNamespace, nodes: list[Element]) -> list[Element]:
    return [*reversed(nodes), nodes[0]]
