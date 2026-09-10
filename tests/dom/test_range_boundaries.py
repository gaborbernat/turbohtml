from __future__ import annotations

import sys
from typing import Final

import pytest

from turbohtml import CData, Comment, Element, Node, Range, Text


@pytest.mark.parametrize(
    "container",
    [
        pytest.param(Text("é😀"), id="text"),
        pytest.param(Comment("é😀"), id="comment"),
        pytest.param(CData("é😀"), id="cdata"),
        pytest.param(Element("div", children=[Element("i"), Element("b")]), id="element"),
    ],
)
@pytest.mark.parametrize("offset", [0, 2], ids=["start", "end"])
def test_boundary_endpoint(container: Node, offset: int) -> None:
    boundary: Final = Range(container, offset)
    assert (boundary.start_container, boundary.start_offset, boundary.end_container, boundary.end_offset) == (
        container,
        offset,
        container,
        offset,
    )


@pytest.mark.parametrize(
    "container",
    [
        pytest.param(Text("é😀"), id="text"),
        pytest.param(Comment("é😀"), id="comment"),
        pytest.param(CData("é😀"), id="cdata"),
        pytest.param(Element("div", children=[Element("i"), Element("b")]), id="element"),
    ],
)
@pytest.mark.parametrize(
    "offset", [-sys.maxsize - 1, -1, 3, sys.maxsize], ids=["minimum", "negative", "past", "maximum"]
)
def test_boundary_rejects_invalid_offset(container: Node, offset: int) -> None:
    with pytest.raises(IndexError, match="out of range"):
        Range(container, offset)
