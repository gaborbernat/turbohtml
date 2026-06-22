"""Element.insert_adjacent_html parses a fragment and splices it at a DOM position."""

from __future__ import annotations

import pytest

from turbohtml import Element, parse


def _li(markup: str = "<ul><li>one</li></ul>") -> Element:
    element = parse(markup).find("li")
    assert element is not None
    return element


def test_beforebegin_inserts_among_previous_siblings() -> None:
    element = _li()
    element.insert_adjacent_html("beforebegin", "<li>zero</li>")
    parent = element.parent
    assert parent is not None
    assert parent.html == "<ul><li>zero</li><li>one</li></ul>"


def test_afterend_inserts_among_following_siblings() -> None:
    element = _li()
    element.insert_adjacent_html("afterend", "<li>two</li>")
    parent = element.parent
    assert parent is not None
    assert parent.html == "<ul><li>one</li><li>two</li></ul>"


def test_afterbegin_inserts_as_the_first_children() -> None:
    element = _li("<ul><li><span>kept</span></li></ul>")
    element.insert_adjacent_html("afterbegin", "<em>new</em>")
    assert element.html == "<li><em>new</em><span>kept</span></li>"


def test_afterbegin_into_an_empty_element() -> None:
    element = _li("<ul><li></li></ul>")
    element.insert_adjacent_html("afterbegin", "<em>new</em>")
    assert element.html == "<li><em>new</em></li>"


def test_beforeend_appends_as_the_last_children() -> None:
    element = _li("<ul><li><span>kept</span></li></ul>")
    element.insert_adjacent_html("beforeend", "<em>new</em>")
    assert element.html == "<li><span>kept</span><em>new</em></li>"


def test_position_is_case_insensitive() -> None:
    element = _li()
    element.insert_adjacent_html("BeforeEnd", "<em>x</em>")
    assert element.html == "<li>one<em>x</em></li>"


@pytest.mark.parametrize(
    "position",
    [
        pytest.param("beforebegin", id="beforebegin"),
        pytest.param("afterend", id="afterend"),
    ],
)
def test_sibling_positions_keep_argument_order(position: str) -> None:
    element = _li()
    element.insert_adjacent_html(position, "<a></a><b></b>")
    parent = element.parent
    assert parent is not None
    expected = "<ul><a></a><b></b><li>one</li></ul>" if position == "beforebegin" else "<ul><li>one</li><a></a><b></b></ul>"
    assert parent.html == expected


def test_inserts_in_the_parent_context() -> None:
    # a bare <td> only survives when the parse context is the <tr> it joins
    element = parse("<table><tr><td>a</td></tr></table>").find("td")
    assert element is not None
    element.insert_adjacent_html("afterend", "<td>b</td>")
    row = element.parent
    assert row is not None
    assert row.html == "<tr><td>a</td><td>b</td></tr>"


def test_beforebegin_on_a_detached_element_raises() -> None:
    with pytest.raises(ValueError, match="need an element parent"):
        Element("div").insert_adjacent_html("beforebegin", "<b>x</b>")


def test_afterend_on_the_root_element_raises() -> None:
    html = parse("<p>x</p>").find("html")
    assert html is not None  # its parent is the document, not an element
    with pytest.raises(ValueError, match="need an element parent"):
        html.insert_adjacent_html("afterend", "<b>x</b>")


def test_rejects_an_unknown_position() -> None:
    with pytest.raises(ValueError, match="position must be"):
        _li().insert_adjacent_html("middle", "<b>x</b>")


def test_rejects_a_non_str_position() -> None:
    with pytest.raises(TypeError):
        _li().insert_adjacent_html(5, "<b>x</b>")  # ty: ignore[invalid-argument-type]  # position must be a str


def test_rejects_a_non_str_html() -> None:
    with pytest.raises(TypeError):
        _li().insert_adjacent_html("beforeend", 5)  # ty: ignore[invalid-argument-type]  # html must be a str


def test_rejects_a_lone_surrogate_context_tag() -> None:
    # 'beforeend' parses in the element's own context, whose tag must encode to UTF-8
    element = Element("\ud800")
    with pytest.raises(UnicodeEncodeError):
        element.insert_adjacent_html("beforeend", "<b>x</b>")
