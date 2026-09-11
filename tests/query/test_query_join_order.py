"""Join batching must preserve the first encounter of each result."""

from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element, parse
from turbohtml.query import Query


@pytest.mark.parametrize(
    ("selected", "expected"),
    [
        pytest.param(["a"], ["b", "c"], id="single-root"),
        pytest.param(["a", "b"], ["b", "c", "a"], id="same-parent"),
        pytest.param(["a", "b", "c"], ["b", "c", "a"], id="complete-parent"),
        pytest.param(["b", "a"], ["a", "c", "b"], id="reverse-roots"),
        pytest.param(["a", "d", "b"], ["b", "c", "e", "a"], id="interleaved-parents"),
    ],
)
def test_query_sibling_encounter_order(selected: list[str], expected: list[str]) -> None:
    document: Final = parse(
        '<main><p id="a"></p><b id="b"></b><i id="c"></i></main><aside><p id="d"></p><b id="e"></b></aside>'
    )
    roots: Final = [document.select_one(f"#{name}") for name in selected]
    assert all(isinstance(node, Element) for node in roots)
    assert [
        node.attrs["id"] for node in Query(node for node in roots if isinstance(node, Element)).siblings()
    ] == expected


def test_query_sibling_cross_tree_order() -> None:
    first: Final = Query('<main><p id="a"></p><p id="b"></p></main>')("p")
    second: Final = Query('<main><p id="c"></p><p id="d"></p></main>')("p")
    assert [node.attrs["id"] for node in Query([first[0], second[0], first[1], second[1]]).siblings()] == [
        "b",
        "d",
        "a",
        "c",
    ]


def test_query_sibling_detached_root() -> None:
    assert list(Query([Element("p")]).siblings()) == []
