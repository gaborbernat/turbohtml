"""Structural edits on the mutable tree: append, insert, move, replace, extract."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import Comment, Element, Text, parse

if TYPE_CHECKING:
    from collections.abc import Iterator


def test_append_constructed_child() -> None:
    div = Element("div")
    div.append(Element("span"))
    div.append(Text("hi"))
    assert div.html == "<div><span></span>hi</div>"


def test_append_moves_within_same_tree() -> None:
    doc = parse("<ul><li>a</li><li>b</li></ul>")
    ul = doc.find("ul")
    assert ul is not None
    first = doc.find("li")
    assert first is not None
    ul.append(first)  # a single-parent node relocates rather than duplicating
    assert ul.html == "<ul><li>b</li><li>a</li></ul>"


def test_append_adopts_subtree_from_another_tree() -> None:
    doc = parse('<section id=s class="box wide"><b>x</b><i>y</i></section>')
    section = doc.find("section")
    assert section is not None
    box = Element("div")
    box.append(section)
    assert box.html == '<div><section id="s" class="box wide"><b>x</b><i>y</i></section></div>'
    assert doc.find("section") is None  # the source tree no longer holds it


def test_append_adopts_every_attribute_shape() -> None:
    # data-custom-xyz is no known atom, so adoption must re-intern its name across
    # trees; the valueless and empty-but-present values must survive the copy too
    src = Element("x", {"data-custom-xyz": "1", "disabled": None, "value": ""})
    box = Element("div")
    box.append(src)
    held = box.find("x")
    assert held is not None
    assert held.attrs["data-custom-xyz"] == "1"
    assert held.attrs["disabled"] is None  # a valueless attribute stays valueless
    value = held.attrs["value"]
    assert value is not None  # an empty value stays present, unlike a valueless one
    assert not value  # but is empty


def test_append_adopts_an_empty_data_node() -> None:
    box = Element("div")
    box.append(Comment(""))  # an empty-data node copies with no character buffer
    assert box.html == "<div><!----></div>"


def test_append_rejects_non_node() -> None:
    with pytest.raises(TypeError, match="must be a node"):
        Element("p").append("x")  # ty: ignore[invalid-argument-type]  # child must be a node


def test_append_rejects_document() -> None:
    doc = parse("<p></p>")
    with pytest.raises(TypeError, match="Document cannot be inserted"):
        Element("p").append(doc)


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


def test_insert_at_index() -> None:
    p = Element("p")
    p.append(Element("a"))
    p.append(Element("c"))
    p.insert(1, Element("b"))
    assert p.html == "<p><a></a><b></b><c></c></p>"


def test_insert_negative_index_counts_from_end() -> None:
    p = Element("p")
    p.append(Element("a"))
    p.append(Element("c"))
    p.insert(-1, Element("b"))  # like list.insert, -1 lands before the last child
    assert p.html == "<p><a></a><b></b><c></c></p>"


def test_insert_negative_index_clamps_to_start() -> None:
    p = Element("p")
    p.append(Element("a"))
    p.insert(-100, Text("S"))
    assert p.html == "<p>S<a></a></p>"


def test_insert_past_end_appends() -> None:
    p = Element("p")
    p.append(Element("a"))
    p.insert(100, Text("E"))
    assert p.html == "<p><a></a>E</p>"


def test_insert_moving_a_node_onto_its_own_slot_appends() -> None:
    doc = parse("<p><a></a><b></b><c></c></p>")
    p = doc.find("p")
    assert p is not None
    middle = doc.find("b")
    assert middle is not None
    p.insert(1, middle)  # the reference slot is the moved node itself, so it tails
    assert p.html == "<p><a></a><c></c><b></b></p>"


def test_insert_rejects_bad_arguments() -> None:
    with pytest.raises(TypeError):
        Element("p").insert("x", Text("y"))  # ty: ignore[invalid-argument-type]  # index must be an int


def test_insert_rejects_non_node_child() -> None:
    with pytest.raises(TypeError, match="must be a node"):
        Element("p").insert(0, "x")  # ty: ignore[invalid-argument-type]  # child must be a node


def test_clear_detaches_every_child() -> None:
    doc = parse("<ul><li>a</li><li>b</li></ul>")
    ul = doc.find("ul")
    assert ul is not None
    ul.clear()
    assert ul.html == "<ul></ul>"


def test_clear_on_empty_element_is_a_noop() -> None:
    div = Element("div")
    div.clear()
    assert div.html == "<div></div>"


def test_insert_before_a_sibling() -> None:
    doc = parse("<ul><li>a</li></ul>")
    li = doc.find("li")
    assert li is not None
    li.insert_before(Comment("note"))
    ul = doc.find("ul")
    assert ul is not None
    assert ul.html == "<ul><!--note--><li>a</li></ul>"


def test_insert_after_a_middle_sibling() -> None:
    doc = parse("<ul><li>a</li><li>c</li></ul>")
    first = doc.find("li")
    assert first is not None
    first.insert_after(Element("b"))
    ul = doc.find("ul")
    assert ul is not None
    assert ul.html == "<ul><li>a</li><b></b><li>c</li></ul>"


def test_insert_after_the_last_sibling_appends() -> None:
    doc = parse("<ul><li>a</li></ul>")
    last = doc.find("li")
    assert last is not None
    last.insert_after(Element("b"))
    ul = doc.find("ul")
    assert ul is not None
    assert ul.html == "<ul><li>a</li><b></b></ul>"


@pytest.mark.parametrize("method", ["insert_before", "insert_after", "replace_with"])
def test_sibling_edit_needs_a_parent(method: str) -> None:
    with pytest.raises(ValueError, match="no parent"):
        getattr(Text("x"), method)(Text("y"))


@pytest.mark.parametrize("method", ["insert_before", "insert_after", "replace_with"])
def test_sibling_edit_with_self_is_a_noop(method: str) -> None:
    doc = parse("<ul><li>a</li><li>b</li></ul>")
    li = doc.find("li")
    assert li is not None
    getattr(li, method)(li)
    ul = doc.find("ul")
    assert ul is not None
    assert ul.html == "<ul><li>a</li><li>b</li></ul>"


@pytest.mark.parametrize("method", ["insert_before", "insert_after", "replace_with"])
def test_sibling_edit_rejects_non_node(method: str) -> None:
    doc = parse("<ul><li>a</li></ul>")
    li = doc.find("li")
    assert li is not None
    with pytest.raises(TypeError, match="must be a node"):
        getattr(li, method)("x")


def test_replace_with_swaps_a_node() -> None:
    doc = parse("<p><b>x</b></p>")
    bold = doc.find("b")
    assert bold is not None
    bold.replace_with(Text("plain"))
    p = doc.find("p")
    assert p is not None
    assert p.html == "<p>plain</p>"
    assert bold.parent is None  # the replaced node is detached, still usable


def test_extract_detaches_and_returns_self() -> None:
    doc = parse("<div><span>s</span></div>")
    span = doc.find("span")
    assert span is not None
    out = span.extract()
    assert out is span
    assert span.parent is None
    div = doc.find("div")
    assert div is not None
    assert div.html == "<div></div>"


def test_extract_an_extracted_node_reinserts() -> None:
    doc = parse("<div><span>s</span></div>")
    span = doc.find("span")
    assert span is not None
    span.extract()
    box = Element("section")
    box.append(span)
    assert box.html == "<section><span>s</span></section>"


def test_extract_a_standalone_node_is_a_noop() -> None:
    node = Element("div")
    assert node.extract() is node  # a node with no parent extracts to itself


def test_insert_before_takes_several_nodes_in_order() -> None:
    doc = parse("<ul><li>b</li></ul>")
    li = doc.find("li")
    assert li is not None
    li.insert_before(Text("A"), Comment("c"))
    ul = doc.find("ul")
    assert ul is not None
    assert ul.html == "<ul>A<!--c--><li>b</li></ul>"


def test_insert_after_takes_several_nodes_in_order() -> None:
    doc = parse("<ul><li>a</li></ul>")
    li = doc.find("li")
    assert li is not None
    li.insert_after(Element("x"), Element("y"))  # the cursor keeps argument order
    ul = doc.find("ul")
    assert ul is not None
    assert ul.html == "<ul><li>a</li><x></x><y></y></ul>"


def test_replace_with_takes_several_nodes() -> None:
    doc = parse("<p><b>x</b></p>")
    bold = doc.find("b")
    assert bold is not None
    bold.replace_with(Text("1"), Text("2"))
    p = doc.find("p")
    assert p is not None
    assert p.html == "<p>12</p>"


def test_replace_with_nothing_just_removes() -> None:
    doc = parse("<p><b>x</b>y</p>")
    bold = doc.find("b")
    assert bold is not None
    bold.replace_with()  # no replacement nodes drops the node
    p = doc.find("p")
    assert p is not None
    assert p.html == "<p>y</p>"


def test_wrap_puts_a_node_inside_an_element() -> None:
    doc = parse("<div><span>s</span></div>")
    span = doc.find("span")
    assert span is not None
    wrapper = span.wrap(Element("a"))
    assert wrapper.tag == "a"  # wrap returns the wrapper
    div = doc.find("div")
    assert div is not None
    assert div.html == "<div><a><span>s</span></a></div>"


def test_wrap_a_standalone_node() -> None:
    wrapped = Text("hi").wrap(Element("em"))
    assert wrapped.html == "<em>hi</em>"


def test_wrap_rejects_a_non_element_wrapper() -> None:
    with pytest.raises(TypeError, match="must be an element"):
        Text("x").wrap(Text("y"))  # ty: ignore[invalid-argument-type]  # a Text cannot hold children


def test_wrap_rejects_a_non_node_wrapper() -> None:
    with pytest.raises(TypeError, match="must be an element"):
        Text("x").wrap("y")  # ty: ignore[invalid-argument-type]  # wrapper must be a node


def test_wrap_in_an_ancestor_is_a_cycle() -> None:
    doc = parse("<div><p><span></span></p></div>")
    span = doc.find("span")
    div = doc.find("div")
    assert span is not None
    assert div is not None
    with pytest.raises(ValueError, match="own subtree"):
        span.wrap(div)


def test_wrap_a_document_is_rejected() -> None:
    doc = parse("<p></p>")
    with pytest.raises(TypeError, match="Document cannot be inserted"):
        doc.wrap(Element("div"))


def test_unwrap_replaces_an_element_with_its_children() -> None:
    doc = parse("<div><b>x<i>y</i></b></div>")
    bold = doc.find("b")
    assert bold is not None
    out = bold.unwrap()
    assert out is bold  # unwrap returns the now-detached element
    div = doc.find("div")
    assert div is not None
    assert div.html == "<div>x<i>y</i></div>"


def test_unwrap_a_childless_node_just_removes_it() -> None:
    doc = parse("<div><span></span>t</div>")
    span = doc.find("span")
    assert span is not None
    span.unwrap()
    div = doc.find("div")
    assert div is not None
    assert div.html == "<div>t</div>"


def test_unwrap_needs_a_parent() -> None:
    with pytest.raises(ValueError, match="no parent"):
        Element("div").unwrap()


def test_decompose_detaches_and_returns_none() -> None:
    doc = parse("<div><span>s</span>t</div>")
    span = doc.find("span")
    assert span is not None
    assert span.decompose() is None
    div = doc.find("div")
    assert div is not None
    assert div.html == "<div>t</div>"


def test_normalize_merges_adjacent_text_and_drops_empties() -> None:
    p = Element("p")
    # the Comment is neither text nor element, so it breaks a run without merging
    p.extend([Text("a"), Text(""), Text("b"), Comment("c"), Element("br"), Text("d")])
    p.normalize()
    assert p.html == "<p>ab<!--c--><br>d</p>"
    assert len(p) == 4  # the run a/""/b collapsed into one Text node


def test_normalize_drops_a_leading_empty_text_node() -> None:
    p = Element("p")
    p.extend([Text(""), Text("x")])
    p.normalize()
    assert [type(child).__name__ for child in p] == ["Text"]
    assert p.html == "<p>x</p>"


def test_normalize_recurses_into_child_elements() -> None:
    p = Element("p")
    inner = Element("b")
    inner.extend([Text("x"), Text("y")])
    p.append(inner)
    p.normalize()
    bold = p.find("b")
    assert bold is not None
    assert len(bold) == 1  # the nested adjacent text merged too
    assert bold.html == "<b>xy</b>"
