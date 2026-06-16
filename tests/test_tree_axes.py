"""Traversal axes: sibling, document-order following, and ancestor-excluding preceding."""

from __future__ import annotations

from typing import TYPE_CHECKING

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


def test_next_siblings_are_forward_only() -> None:
    assert _tags(_find(_DOC, "h2").next_siblings) == ["p", "ul"]
    assert _tags(_find(_DOC, "ul").next_siblings) == []


def test_previous_siblings_are_nearest_first() -> None:
    assert _tags(_find(_DOC, "ul").previous_siblings) == ["p", "h2"]
    assert _tags(_find(_DOC, "h2").previous_siblings) == []


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


def test_strings_yields_every_text_node_in_order() -> None:
    div = _find("<div><p> hi </p><p>  </p><p>bye</p></div>", "div")
    assert list(div.strings) == [" hi ", "  ", "bye"]


def test_stripped_strings_trims_and_skips_blank_runs() -> None:
    div = _find("<div><p> hi </p><p>  </p><p>bye</p></div>", "div")
    assert list(div.stripped_strings) == ["hi", "bye"]
