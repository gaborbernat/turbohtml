"""matches() and closest(): self-test and nearest-ancestor CSS matching."""

from __future__ import annotations

import pytest

from turbohtml import parse

_DOC = (
    '<section id="s" class="box">'
    '<article class="post"><h2>T</h2><p class="lead">one <a href="/x">link</a></p></article>'
    "</section>"
)


def test_matches_self() -> None:
    a = parse(_DOC).select_one("a")
    assert a is not None
    assert a.matches("a")
    assert a.matches('[href="/x"]')
    assert not a.matches("p")


def test_matches_considers_ancestors_and_siblings() -> None:
    a = parse(_DOC).select_one("a")
    assert a is not None
    assert a.matches("section a")  # a has a section ancestor
    assert a.matches("article p > a")  # full chain holds
    assert not a.matches("h2 a")  # no h2 ancestor


def test_matches_non_element_is_false() -> None:
    document = parse(_DOC)
    assert not document.matches("section")  # the Document node is not an element
    h2 = document.select_one("h2")
    assert h2 is not None
    text = h2.children[0]
    assert not text.matches("h2")  # a Text node never matches


def test_matches_rejects_non_str() -> None:
    a = parse(_DOC).select_one("a")
    assert a is not None
    with pytest.raises(TypeError):
        a.matches(123)  # ty: ignore[invalid-argument-type]  # not a str


def test_matches_rejects_invalid_selector() -> None:
    a = parse(_DOC).select_one("a")
    assert a is not None
    with pytest.raises(ValueError, match="selector"):
        a.matches("[")


def test_closest_returns_self_when_it_matches() -> None:
    article = parse(_DOC).select_one("article")
    assert article is not None
    closest = article.closest(".post")
    assert closest is not None
    assert closest.tag == "article"


def test_closest_walks_up_to_an_ancestor() -> None:
    a = parse(_DOC).select_one("a")
    assert a is not None
    section = a.closest("section")
    assert section is not None
    assert section.tag == "section"
    article = a.closest(".post")
    assert article is not None
    assert article.tag == "article"


def test_closest_returns_none_when_nothing_matches() -> None:
    a = parse(_DOC).select_one("a")
    assert a is not None
    assert a.closest("table") is None


def test_closest_from_a_text_node() -> None:
    p = parse(_DOC).select_one("p.lead")
    assert p is not None
    text = p.children[0]
    nearest = text.closest("p")  # a Text node's nearest matching ancestor
    assert nearest is not None
    assert nearest.tag == "p"


def test_closest_rejects_non_str() -> None:
    a = parse(_DOC).select_one("a")
    assert a is not None
    with pytest.raises(TypeError):
        a.closest(123)  # ty: ignore[invalid-argument-type]  # not a str


def test_closest_rejects_invalid_selector() -> None:
    a = parse(_DOC).select_one("a")
    assert a is not None
    with pytest.raises(ValueError, match="selector"):
        a.closest("[")
