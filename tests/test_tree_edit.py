"""Structural edits on the mutable tree: append, insert, move, replace, extract."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import Comment, Document, Element, Node, Text, parse

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def _found(root: Element | Document, selector: str) -> Element:
    """First match of selector in an already-edited tree, asserted present."""
    node = root.find(selector)
    assert node is not None, selector
    return node


def test_append_constructed_child() -> None:
    div = Element("div")
    div.append(Element("span"))
    div.append(Text("hi"))
    assert div.html == "<div><span></span>hi</div>"


def test_append_moves_within_same_tree() -> None:
    doc = parse("<ul><li>a</li><li>b</li></ul>")
    ul = _found(doc, "ul")
    ul.append(_found(doc, "li"))  # a single-parent node relocates rather than duplicating
    assert ul.html == "<ul><li>b</li><li>a</li></ul>"


def test_append_adopts_subtree_from_another_tree() -> None:
    doc = parse('<section id=s class="box wide"><b>x</b><i>y</i></section>')
    box = Element("div")
    box.append(_found(doc, "section"))
    assert box.html == '<div><section id="s" class="box wide"><b>x</b><i>y</i></section></div>'
    assert doc.find("section") is None  # the source tree no longer holds it


def test_append_adopts_every_attribute_shape() -> None:
    # data-custom-xyz is no known atom, so adoption must re-intern its name across
    # trees; the valueless and empty values (both "") must survive the copy too
    source = Element("x", {"data-custom-xyz": "1", "disabled": None, "value": ""})
    box = Element("div")
    box.append(source)
    held = _found(box, "x")
    assert held.attrs["data-custom-xyz"] == "1"
    assert held.attrs["disabled"] == ""  # noqa: PLC1901  # exactly "" (valueless reads empty), not None
    assert held.attrs["value"] == ""  # noqa: PLC1901  # exactly ""


def test_append_adopts_an_empty_data_node() -> None:
    box = Element("div")
    box.append(Comment(""))  # an empty-data node copies with no character buffer
    assert box.html == "<div><!----></div>"


def test_append_rejects_non_node() -> None:
    with pytest.raises(TypeError, match="must be a node"):
        Element("p").append("x")  # ty: ignore[invalid-argument-type]  # child must be a node


def test_append_rejects_document() -> None:
    with pytest.raises(TypeError, match="Document cannot be inserted"):
        Element("p").append(parse("<p></p>"))


def test_append_rejects_cycle() -> None:
    parent = Element("p")
    child = Element("q")
    parent.append(child)
    with pytest.raises(ValueError, match="own subtree"):
        child.append(parent)


def test_extend_appends_each_in_order() -> None:
    ul = Element("ul")
    ul.extend([Element("li"), Text("x"), Comment("c")])
    assert ul.html == "<ul><li></li>x<!--c--></ul>"


def test_extend_rejects_non_iterable() -> None:
    with pytest.raises(TypeError):
        Element("ul").extend(5)  # ty: ignore[invalid-argument-type]  # children must be iterable


def test_extend_rejects_non_node_member() -> None:
    with pytest.raises(TypeError, match="must be a node"):
        Element("ul").extend([Element("li"), 1])  # ty: ignore[invalid-argument-type]  # members must be nodes


def test_extend_propagates_iterator_error() -> None:
    def boom() -> Iterator[Element]:
        yield Element("li")
        msg = "stop"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="stop"):
        Element("ul").extend(boom())


@pytest.mark.parametrize(
    "index",
    # like list.insert, index -1 lands before the last child, not after it
    [pytest.param(1, id="positive"), pytest.param(-1, id="negative-counts-from-end")],
)
def test_insert_places_a_child_between_two_siblings(index: int) -> None:
    paragraph = Element("p")
    paragraph.append(Element("a"))
    paragraph.append(Element("c"))
    paragraph.insert(index, Element("b"))
    assert paragraph.html == "<p><a></a><b></b><c></c></p>"


@pytest.mark.parametrize(
    ("index", "text", "expected"),
    [
        pytest.param(-100, "S", "<p>S<a></a></p>", id="negative-clamps-to-start"),
        pytest.param(100, "E", "<p><a></a>E</p>", id="past-end-appends"),
    ],
)
def test_insert_clamps_out_of_range_index(index: int, text: str, expected: str) -> None:
    paragraph = Element("p")
    paragraph.append(Element("a"))
    paragraph.insert(index, Text(text))
    assert paragraph.html == expected


def test_insert_moving_a_node_onto_its_own_slot_appends() -> None:
    doc = parse("<p><a></a><b></b><c></c></p>")
    paragraph = _found(doc, "p")
    paragraph.insert(1, _found(doc, "b"))  # the reference slot is the moved node itself, so it tails
    assert paragraph.html == "<p><a></a><c></c><b></b></p>"


def test_insert_rejects_bad_arguments() -> None:
    with pytest.raises(TypeError):
        Element("p").insert("x", Text("y"))  # ty: ignore[invalid-argument-type]  # index must be an int


def test_insert_rejects_non_node_child() -> None:
    with pytest.raises(TypeError, match="must be a node"):
        Element("p").insert(0, "x")  # ty: ignore[invalid-argument-type]  # child must be a node


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        pytest.param(lambda: _found(parse("<ul><li>a</li><li>b</li></ul>"), "ul"), "<ul></ul>", id="with-children"),
        pytest.param(lambda: Element("div"), "<div></div>", id="already-empty"),
    ],
)
def test_clear_detaches_every_child(make: Callable[[], Element], expected: str) -> None:
    element = make()
    element.clear()
    assert element.html == expected


@pytest.mark.parametrize(
    ("html", "method", "nodes", "expected"),
    [
        pytest.param(
            "<ul><li>a</li></ul>",
            "insert_before",
            [Comment("note")],
            "<ul><!--note--><li>a</li></ul>",
            id="before-single",
        ),
        pytest.param(
            "<ul><li>a</li><li>c</li></ul>",
            "insert_after",
            [Element("b")],
            "<ul><li>a</li><b></b><li>c</li></ul>",
            id="after-middle",
        ),
        pytest.param(
            "<ul><li>a</li></ul>",
            "insert_after",
            [Element("b")],
            "<ul><li>a</li><b></b></ul>",
            id="after-last-appends",
        ),
        pytest.param(
            "<ul><li>b</li></ul>",
            "insert_before",
            [Text("A"), Comment("c")],
            "<ul>A<!--c--><li>b</li></ul>",
            id="before-multiple-keeps-order",
        ),
        pytest.param(
            "<ul><li>a</li></ul>",
            "insert_after",
            [Element("x"), Element("y")],
            "<ul><li>a</li><x></x><y></y></ul>",
            id="after-multiple-keeps-order",
        ),
    ],
)
def test_sibling_insertion_relative_to_first_li(html: str, method: str, nodes: list[Node], expected: str) -> None:
    doc = parse(html)
    getattr(_found(doc, "li"), method)(*nodes)
    assert _found(doc, "ul").html == expected


_SIBLING_METHODS = [
    pytest.param("insert_before", id="insert_before"),
    pytest.param("insert_after", id="insert_after"),
    pytest.param("replace_with", id="replace_with"),
]


@pytest.mark.parametrize("method", _SIBLING_METHODS)
def test_sibling_edit_needs_a_parent(method: str) -> None:
    with pytest.raises(ValueError, match="no parent"):
        getattr(Text("x"), method)(Text("y"))


@pytest.mark.parametrize("method", _SIBLING_METHODS)
def test_sibling_edit_with_self_is_a_noop(method: str) -> None:
    doc = parse("<ul><li>a</li><li>b</li></ul>")
    getattr(_found(doc, "li"), method)(_found(doc, "li"))  # editing a node relative to itself changes nothing
    assert _found(doc, "ul").html == "<ul><li>a</li><li>b</li></ul>"


@pytest.mark.parametrize("method", _SIBLING_METHODS)
def test_sibling_edit_rejects_non_node(method: str) -> None:
    li = _found(parse("<ul><li>a</li></ul>"), "li")
    with pytest.raises(TypeError, match="must be a node"):
        getattr(li, method)("x")


@pytest.mark.parametrize(
    ("html", "replacements", "expected"),
    [
        pytest.param("<p><b>x</b></p>", [Text("plain")], "<p>plain</p>", id="single"),
        pytest.param("<p><b>x</b></p>", [Text("1"), Text("2")], "<p>12</p>", id="multiple-in-order"),
        pytest.param("<p><b>x</b>y</p>", [], "<p>y</p>", id="none-just-removes"),
    ],
)
def test_replace_with(html: str, replacements: list[Node], expected: str) -> None:
    doc = parse(html)
    bold = _found(doc, "b")
    bold.replace_with(*replacements)
    assert _found(doc, "p").html == expected
    assert bold.parent is None  # the replaced node is detached, still usable


def test_extract_detaches_and_returns_self() -> None:
    doc = parse("<div><span>s</span></div>")
    span = _found(doc, "span")
    assert span.extract() is span
    assert span.parent is None
    assert _found(doc, "div").html == "<div></div>"


def test_extract_an_extracted_node_reinserts() -> None:
    span = _found(parse("<div><span>s</span></div>"), "span")
    span.extract()
    box = Element("section")
    box.append(span)
    assert box.html == "<section><span>s</span></section>"


def test_extract_a_standalone_node_is_a_noop() -> None:
    node = Element("div")
    assert node.extract() is node  # a node with no parent extracts to itself


def test_wrap_puts_a_node_inside_an_element() -> None:
    doc = parse("<div><span>s</span></div>")
    wrapper = _found(doc, "span").wrap(Element("a"))
    assert wrapper.tag == "a"  # wrap returns the wrapper
    assert _found(doc, "div").html == "<div><a><span>s</span></a></div>"


def test_wrap_a_standalone_node() -> None:
    assert Text("hi").wrap(Element("em")).html == "<em>hi</em>"


@pytest.mark.parametrize(
    "wrapper",
    # a Text cannot hold children, and a bare string is not a node at all
    [pytest.param(Text("y"), id="text"), pytest.param("y", id="non-node")],
)
def test_wrap_rejects_a_non_element_wrapper(wrapper: object) -> None:
    with pytest.raises(TypeError, match="must be an element"):
        Text("x").wrap(wrapper)  # ty: ignore[invalid-argument-type]  # wrapper must be an element node


def test_wrap_in_an_ancestor_is_a_cycle() -> None:
    doc = parse("<div><p><span></span></p></div>")
    with pytest.raises(ValueError, match="own subtree"):
        _found(doc, "span").wrap(_found(doc, "div"))


def test_wrap_a_document_is_rejected() -> None:
    with pytest.raises(TypeError, match="Document cannot be inserted"):
        parse("<p></p>").wrap(Element("div"))


def test_unwrap_replaces_an_element_with_its_children() -> None:
    doc = parse("<div><b>x<i>y</i></b></div>")
    bold = _found(doc, "b")
    assert bold.unwrap() is bold  # unwrap returns the now-detached element
    assert _found(doc, "div").html == "<div>x<i>y</i></div>"


def test_unwrap_a_childless_node_just_removes_it() -> None:
    doc = parse("<div><span></span>t</div>")
    _found(doc, "span").unwrap()
    assert _found(doc, "div").html == "<div>t</div>"


def test_unwrap_needs_a_parent() -> None:
    with pytest.raises(ValueError, match="no parent"):
        Element("div").unwrap()


def test_decompose_detaches_and_returns_none() -> None:
    doc = parse("<div><span>s</span>t</div>")
    assert _found(doc, "span").decompose() is None
    assert _found(doc, "div").html == "<div>t</div>"


def test_normalize_merges_adjacent_text_and_drops_empties() -> None:
    paragraph = Element("p")
    # the Comment is neither text nor element, so it breaks a run without merging
    paragraph.extend([Text("a"), Text(""), Text("b"), Comment("c"), Element("br"), Text("d")])
    paragraph.normalize()
    assert paragraph.html == "<p>ab<!--c--><br>d</p>"
    assert len(paragraph) == 4  # the run a/""/b collapsed into one Text node


def test_normalize_drops_a_leading_empty_text_node() -> None:
    paragraph = Element("p")
    paragraph.extend([Text(""), Text("x")])
    paragraph.normalize()
    assert [type(child).__name__ for child in paragraph] == ["Text"]
    assert paragraph.html == "<p>x</p>"


def test_normalize_recurses_into_child_elements() -> None:
    paragraph = Element("p")
    inner = Element("b")
    inner.extend([Text("x"), Text("y")])
    paragraph.append(inner)
    paragraph.normalize()
    bold = _found(paragraph, "b")
    assert len(bold) == 1  # the nested adjacent text merged too
    assert bold.html == "<b>xy</b>"
