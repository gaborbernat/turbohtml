"""Pruning must retain selected subtrees and the paths that reach them."""

from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse


@pytest.mark.parametrize("depth", [pytest.param(1, id="shallow"), pytest.param(100, id="deep")])
@pytest.mark.parametrize("selector", [pytest.param("b", id="leaves"), pytest.param("section, b", id="overlap")])
def test_prune_shared_ancestors(depth: int, selector: str) -> None:
    document: Final = parse(
        "<main>" + "<section>" * depth + "<b>A</b><i>drop</i><b>B</b>" + "</section>" * depth + "<i>outside</i></main>"
    )
    document.prune(selector)
    assert document.xpath("//main//text()") == (["A", "drop", "B"] if selector == "section, b" else ["A", "B"])


def test_prune_keeps_matching_subtree() -> None:
    document: Final = parse("<main><section><b>A</b><i>inside</i></section><i>outside</i></main>")
    document.prune("section, b")
    assert document.xpath("//main//text()") == ["A", "inside"]


def test_prune_detached_subtree_keeps_removed_references() -> None:
    document: Final = parse("<main><section><div><b>A</b><i>drop</i><b>B</b></div></section></main>")
    section: Final = document.select_one("section")
    removed: Final = document.select_one("i")
    assert section is not None
    assert removed is not None
    document.remove("section")
    section.prune("b")
    assert (section.serialize(), removed.serialize(), removed.parent) == (
        "<section><div><b>A</b><b>B</b></div></section>",
        "<i>drop</i>",
        None,
    )
