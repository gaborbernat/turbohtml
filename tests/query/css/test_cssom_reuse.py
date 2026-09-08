from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse
from turbohtml.cssom import computed_style

if TYPE_CHECKING:
    from turbohtml import Document, Element


@pytest.mark.parametrize(
    ("attribute", "value"),
    [pytest.param("style", "color:blue", id="inline"), pytest.param("class", "blue", id="class")],
)
def test_computed_style_after_parent_attribute_change(attribute: str, value: str) -> None:
    document: Final[Document] = parse(
        "<style>.blue {color:blue!important}</style><div style='color:red'><span>x</span></div>"
    )
    parent: Final[Element] = document.select("div")[0]
    child: Final[Element] = document.select("span")[0]
    before: Final[tuple[str, str]] = (computed_style(parent)["color"], computed_style(child)["color"])
    parent.attrs[attribute] = value
    assert (before, computed_style(parent)["color"], computed_style(child)["color"]) == (("red", "red"), "blue", "blue")


def test_computed_style_after_parent_attribute_removal() -> None:
    document: Final[Document] = parse("<div style='color:red'><span>x</span></div>")
    parent: Final[Element] = document.select("div")[0]
    child: Final[Element] = document.select("span")[0]
    before: Final[str] = computed_style(child)["color"]
    del parent.attrs["style"]
    assert (before, computed_style(child)["color"]) == ("red", "canvastext")


def test_computed_style_after_sibling_attribute_change() -> None:
    document: Final[Document] = parse("<style>.blue + div {color:blue}</style><aside></aside><div>x</div>")
    child: Final[Element] = document.select("div")[0]
    before: Final[str] = computed_style(child)["color"]
    document.select("aside")[0].attrs["class"] = "blue"
    assert (before, computed_style(child)["color"]) == ("canvastext", "blue")


def test_computed_style_reuses_parent_across_children() -> None:
    document: Final[Document] = parse("<div style='color:red'><span>a</span><b>b</b><i>c</i></div>")
    assert [computed_style(element)["color"] for element in document.select("div, span, b, i")] == ["red"] * 4


def test_computed_style_snapshot_survives_later_resolution() -> None:
    document: Final[Document] = parse("<div style='color:red'>a</div><div style='color:blue'>b</div>")
    first: Final = computed_style(document.select("div")[0])
    second: Final = computed_style(document.select("div")[1])
    assert (first["color"], second["color"], computed_style(document.select("div")[0])["color"]) == (
        "red",
        "blue",
        "red",
    )
