from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element
from turbohtml.query import Query


@pytest.mark.parametrize(
    ("indices", "expected"),
    [
        pytest.param([0, 1, 2], ["left", "right"], id="repeated-parent"),
        pytest.param([2, 0, 1], ["right", "left"], id="reverse-groups"),
        pytest.param([0, 2, 1], ["left", "right"], id="interleaved-groups"),
    ],
)
def test_query_parent_encounter_order(indices: list[int], expected: list[str]) -> None:
    children: Final = Query('<main id="left"><p></p><p></p></main><aside id="right"><p></p></aside>')("p")
    assert [node.attrs["id"] for node in Query(children[index] for index in indices).parent()] == expected


def test_query_parent_cross_tree_order() -> None:
    first: Final = Query('<main id="left"><p></p><p></p></main>')("p")
    second: Final = Query('<main id="right"><p></p></main>')("p")
    assert [node.attrs["id"] for node in Query([first[0], second[0], first[1]]).parent()] == ["left", "right"]


def test_query_parent_cross_tree_ownership() -> None:
    first: Final = Query('<main id="left"><p></p><p></p></main>')("p")
    second: Final = Query('<main id="right"><p></p></main>')("p")
    parents: Final = Query([first[0], second[0], first[1]]).parent()
    parents[0].attrs["id"] = "changed"
    assert [node.attrs["id"] for node in first.parent()] == ["changed"]


def test_query_parent_detached_root() -> None:
    assert list(Query([Element("p")]).parent()) == []
