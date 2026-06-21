"""The per-tree compiled-XPath cache is transparent: it must never change results.

It exercises the cache's hit (front and non-front), distinct-but-equal key, and
eviction paths while asserting the answers stay correct.
"""

from __future__ import annotations

import pytest

import turbohtml
from turbohtml import Element

HTML = "<html><body><div><p>a</p><p>b</p></div><a href='/x'>x</a></body></html>"


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


def tags(result: object) -> list[str]:
    assert isinstance(result, list)
    return [node.tag for node in result if isinstance(node, Element)]


def test_repeated_query_is_consistent(doc: turbohtml.Node) -> None:
    for _ in range(5):
        assert tags(doc.xpath("//p")) == ["p", "p"]


def test_move_to_front(doc: turbohtml.Node) -> None:
    # //p falls behind //a in the cache, then is queried again from a non-front slot
    doc.xpath("//p")
    doc.xpath("//a")
    assert tags(doc.xpath("//p")) == ["p", "p"]


def test_distinct_but_equal_key_hits_same_entry(doc: turbohtml.Node) -> None:
    name = "p"
    first = f"//{name}"
    second = f"//{name}"
    assert first is not second  # two distinct str objects with equal content
    doc.xpath(first)
    assert tags(doc.xpath(second)) == ["p", "p"]


def test_eviction_recompiles(doc: turbohtml.Node) -> None:
    assert tags(doc.xpath("//p")) == ["p", "p"]
    # fill past the cache capacity with distinct expressions, evicting //p
    for index in range(20):
        assert doc.xpath(f"//missing{index}") == []
    # //p was evicted; it must recompile to the same answer
    assert tags(doc.xpath("//p")) == ["p", "p"]


def test_compile_error_after_caching(doc: turbohtml.Node) -> None:
    doc.xpath("//p")  # populate the cache first
    with pytest.raises(ValueError, match="node test"):
        doc.xpath("//")
