"""Element.set_text replaces the children with one verbatim Text node."""

from __future__ import annotations

import pytest

from turbohtml import Element, parse


def _p(markup: str = "<p><b>x</b>y</p>") -> Element:
    element = parse(markup).find("p")
    assert element is not None
    return element


def test_replaces_children_with_text() -> None:
    element = _p()
    element.set_text("Tom & Jerry")
    assert element.html == "<p>Tom &amp; Jerry</p>"  # the ampersand is escaped, not parsed
    assert len(element) == 1


def test_markup_in_the_argument_is_not_parsed() -> None:
    element = _p("<p></p>")
    element.set_text("<b>not bold</b>")
    assert element.text == "<b>not bold</b>"
    assert element.find("b") is None  # the angle brackets are text, not an element


def test_empty_string_clears() -> None:
    element = _p()
    element.set_text("")
    assert element.html == "<p></p>"
    assert len(element) == 0


def test_matches_the_text_setter() -> None:
    one = _p()
    other = _p()
    one.set_text("same")
    other.text = "same"
    assert one.html == other.html


def test_constructed_element_in_isolation() -> None:
    element = Element("span")
    element.set_text("hi")
    assert element.html == "<span>hi</span>"


def test_rejects_non_str() -> None:
    with pytest.raises(TypeError, match="text must be a str"):
        _p().set_text(5)  # ty: ignore[invalid-argument-type]  # text must be a str
