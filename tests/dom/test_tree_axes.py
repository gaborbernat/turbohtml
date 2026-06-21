"""Traversal axes: sibling, document-order following, and ancestor-excluding preceding."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import Element, Text, parse

if TYPE_CHECKING:
    from collections.abc import Iterable

    from turbohtml import Node

_DOC = "<section><h2>T</h2><p>one</p><ul><li>a</li><li>b</li></ul></section><footer>f</footer>"


def _tags(nodes: Iterable[Node]) -> list[str]:
    return [node.tag for node in nodes if isinstance(node, Element)]


def _find(html: str, tag: str) -> Element:
    element = parse(html).find(tag)
    assert element is not None
    return element


@pytest.mark.parametrize(
    ("tag", "axis", "expected"),
    [
        pytest.param("h2", "next_siblings", ["p", "ul"], id="next-forward"),
        pytest.param("ul", "next_siblings", [], id="next-at-end"),
        pytest.param("ul", "previous_siblings", ["p", "h2"], id="previous-nearest-first"),
        pytest.param("h2", "previous_siblings", [], id="previous-at-start"),
    ],
)
def test_sibling_axes(tag: str, axis: str, expected: list[str]) -> None:
    assert _tags(getattr(_find(_DOC, tag), axis)) == expected


def test_following_excludes_own_subtree() -> None:
    following = list(_find(_DOC, "h2").following)
    assert _tags(following) == ["p", "ul", "li", "li", "footer"]
    # the heading's own text child is part of its subtree, so it is not "following"
    assert "T" not in [node.data for node in following if isinstance(node, Text)]


def test_following_at_document_end_is_empty() -> None:
    assert _tags(_find(_DOC, "footer").following) == []


def test_preceding_is_reverse_order_excluding_ancestors() -> None:
    preceding = _find(_DOC, "ul").preceding
    # nearest first, and the enclosing <section>/<body>/<html> ancestors are absent
    assert _tags(preceding) == ["p", "h2", "head"]


def test_preceding_of_root_is_empty() -> None:
    root = parse(_DOC).root
    assert root is not None
    assert list(root.preceding) == []


@pytest.mark.parametrize(
    ("axis", "expected"),
    [
        pytest.param("strings", [" hi ", "  ", "bye"], id="strings-verbatim"),
        pytest.param("stripped_strings", ["hi", "bye"], id="stripped-skips-blank-runs"),
    ],
)
def test_text_iterators(axis: str, expected: list[str]) -> None:
    div = _find("<div><p> hi </p><p>  </p><p>bye</p></div>", "div")
    assert list(getattr(div, axis)) == expected
