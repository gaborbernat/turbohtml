from __future__ import annotations

from typing import Final

import pytest

from turbohtml.query import Query, SelectorSyntaxError


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        pytest.param("main", ["first", "second"], id="shared-ancestors"),
        pytest.param(":scope", ["a", "c", "b"], id="scope-per-element"),
        pytest.param("aside", [], id="no-matches"),
    ],
)
def test_query_closest_cross_tree_order(selector: str, expected: list[str]) -> None:
    first: Final = Query('<main id="first"><p id="a"></p><p id="b"></p></main>')("p")
    second: Final = Query('<main id="second"><p id="c"></p></main>')("p")
    assert [node.attrs["id"] for node in Query([first[0], second[0], first[1]]).closest(selector)] == expected


def test_query_closest_parent_ownership() -> None:
    selected: Final = Query("<main><p>x</p><p>y</p></main>")("p").closest("main")
    selected.attr("id", "retained")
    assert selected[0].serialize() == '<main id="retained"><p>x</p><p>y</p></main>'


def test_query_closest_invalid_selector() -> None:
    with pytest.raises(SelectorSyntaxError):
        Query("<p>x</p>")("p").closest("[")
