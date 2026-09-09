from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml


@pytest.mark.parametrize("size", [pytest.param(size, id=str(size)) for size in (0, 1, 15, 16, 17, 32, 64)])
@pytest.mark.parametrize(
    "operation", [pytest.param("intersection", id="intersection"), pytest.param("difference", id="difference")]
)
def test_set_filter_preserves_nodes(size: int, operation: str) -> None:
    document: Final = parse_xml(
        "<root>" + "".join(f'<item id="{index}">same</item>' for index in range(size)) + "</root>"
    )
    assert document.xpath(f"set:{operation}(//item, //item[position() mod 2 = 0])/@id") == [
        str(index) for index in range(size) if (index % 2 == 1) == (operation == "intersection")
    ]


@pytest.mark.parametrize(
    "operation", [pytest.param("intersection", id="intersection"), pytest.param("difference", id="difference")]
)
def test_set_filter_distinguishes_attributes(operation: str) -> None:
    document: Final = parse_xml("<root>" + '<item a="same" b="same"/>' * 64 + "</root>")
    assert document.xpath(f"set:{operation}(//item/@*, //item/@a)") == ["same"] * 64


@pytest.mark.parametrize("size", [pytest.param(size, id=str(size)) for size in (0, 1, 15, 16, 17, 64)])
@pytest.mark.parametrize(
    ("right", "overlap"),
    [pytest.param("//right/item", False, id="disjoint"), pytest.param("//item", True, id="first-overlap")],
)
def test_sets_share_a_node(size: int, right: str, *, overlap: bool) -> None:
    document: Final = parse_xml(f"<root><left>{'<item/>' * size}</left><right>{'<item/>' * size}</right></root>")
    assert document.xpath(f"set:has-same-node(//left/item, {right})") is (overlap and size > 0)


def test_sets_share_a_later_node() -> None:
    document: Final = parse_xml("<root>" + "<item/>" * 64 + "</root>")
    assert document.xpath("set:has-same-node(//item, //item[position() > 32])") is True
