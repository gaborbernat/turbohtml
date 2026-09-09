from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        pytest.param((), (), (False, False), id="empty"),
        pytest.param(("a",) * 16, (), (False, False), id="empty-right"),
        pytest.param((), ("a",) * 16, (False, False), id="empty-left"),
        pytest.param(("a",) * 15, ("b",) * 16, (False, True), id="small-left"),
        pytest.param(("a",) * 16, ("b",) * 15, (False, True), id="small-right"),
        pytest.param(("a",) * 16, ("b",) * 16, (False, True), id="disjoint"),
        pytest.param(("a",) * 32, ("a",) * 32, (True, False), id="equal"),
        pytest.param(("a",) * 31 + ("b",), ("c",) * 31 + ("b",), (True, True), id="late-match"),
        pytest.param(("a",) * 31 + ("b",), ("a",) * 32, (True, True), id="unequal-left"),
        pytest.param(("a",) * 32, ("a",) * 31 + ("b",), (True, True), id="unequal-right"),
        pytest.param(("",) * 16, ("",) * 16, (True, False), id="empty-strings"),
        pytest.param(("é",) * 16, ("e\u0301",) * 16, (False, True), id="no-normalization"),
        pytest.param(("雪𐀀",) * 16, ("雪𐀀",) * 16, (True, False), id="wide-unicode"),
    ],
)
@pytest.mark.parametrize(
    ("operation", "index"), [pytest.param("=", 0, id="equal"), pytest.param("!=", 1, id="unequal")]
)
def test_node_set_value_comparison(
    left: tuple[str, ...], right: tuple[str, ...], expected: tuple[bool, bool], operation: str, index: int
) -> None:
    document: Final = parse_xml(
        "<root>"
        + "".join(f"<left>{value}</left>" for value in left)
        + "".join(f"<right>{value}</right>" for value in right)
        + "</root>"
    )
    assert document.xpath(f"//left {operation} //right") is expected[index]


def test_comparison_uses_attribute_values() -> None:
    document: Final = parse_xml("<root>" + '<item left="same" right="same"/>' * 32 + "</root>")
    assert document.xpath("//item/@left = //item/@right") is True


def test_comparison_uses_descendant_text() -> None:
    document: Final = parse_xml("<root>" + "<left>a<b>b</b>c</left><right>abc</right>" * 32 + "</root>")
    assert document.xpath("//left = //right") is True


@pytest.mark.parametrize(
    "selection", [pytest.param("//item", id="elements"), pytest.param("//item/@value", id="attributes")]
)
def test_comparison_same_nodes(selection: str) -> None:
    document: Final = parse_xml("<root>" + '<item value="same">same</item>' * 32 + "</root>")
    assert document.xpath(f"{selection} = {selection}") is True
