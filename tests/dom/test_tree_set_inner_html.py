"""Element.set_inner_html parses a fragment in context and replaces the children."""

from __future__ import annotations

import pytest

from turbohtml import Element, Namespace, parse


def _div(markup: str = "<div><b>old</b>text</div>") -> Element:
    element = parse(markup).find("div")
    assert element is not None
    return element


def test_replaces_existing_children() -> None:
    element = _div()
    element.set_inner_html("<i>new</i>")
    assert element.html == "<div><i>new</i></div>"
    assert len(element) == 1


def test_parses_markup_into_a_subtree() -> None:
    element = _div("<div></div>")
    element.set_inner_html("<ul><li>a</li><li>b</li></ul>")
    items = element.find_all("li")
    assert [item.text for item in items] == ["a", "b"]


def test_empty_string_clears() -> None:
    element = _div()
    element.set_inner_html("")
    assert element.html == "<div></div>"
    assert len(element) == 0


def test_repairs_malformed_markup_like_the_parser() -> None:
    element = _div("<div></div>")
    element.set_inner_html("<p>a<p>b")  # the parser closes each <p> implicitly
    assert element.html == "<div><p>a</p><p>b</p></div>"


def test_escaped_text_round_trips() -> None:
    element = _div("<div></div>")
    element.set_inner_html("a &amp; b &lt; c")
    assert element.text == "a & b < c"


def test_parses_in_a_table_context() -> None:
    # a bare <tr> only survives the fragment parse when the context is a table section
    element = parse("<table><tbody></tbody></table>").find("tbody")
    assert element is not None
    element.set_inner_html("<tr><td>cell</td></tr>")
    assert element.html == "<tbody><tr><td>cell</td></tr></tbody>"


def test_parses_in_an_svg_context() -> None:
    element = parse("<svg></svg>").find("svg")
    assert element is not None
    element.set_inner_html("<rect></rect>")
    rect = element.find("rect")
    assert rect is not None
    assert rect.namespace is Namespace.SVG  # the rect parsed as an SVG element, not HTML


def test_parses_in_a_math_context() -> None:
    element = parse("<math></math>").find("math")
    assert element is not None
    element.set_inner_html("<mi>x</mi>")
    mi = element.find("mi")
    assert mi is not None
    assert mi.namespace is Namespace.MATHML


def test_constructed_element_in_isolation() -> None:
    element = Element("section")
    element.set_inner_html("<h1>Title</h1>")
    assert element.html == "<section><h1>Title</h1></section>"


def test_rejects_non_str() -> None:
    with pytest.raises(TypeError, match="html must be a str"):
        _div().set_inner_html(5)  # ty: ignore[invalid-argument-type]  # html must be a str


def test_rejects_a_lone_surrogate_tag_name() -> None:
    # the element's tag name is the fragment context, which must encode to UTF-8
    element = Element("\ud800")
    with pytest.raises(UnicodeEncodeError):
        element.set_inner_html("<b>x</b>")
