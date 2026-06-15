"""parse()/parse_fragment() entry points and the shared Node protocol."""

from __future__ import annotations

import gc
from typing import TYPE_CHECKING

import pytest

from turbohtml import Comment, Doctype, Document, Element, Namespace, Node, Text, parse, parse_fragment

if TYPE_CHECKING:
    from collections.abc import Callable


def test_parse_returns_document() -> None:
    doc = parse("<p>hi</p>")
    assert isinstance(doc, Document)
    assert doc.root is not None
    assert doc.root.tag == "html"


def test_root_skips_leading_non_elements() -> None:
    doc = parse("<!-- lead --><!DOCTYPE html><html><body>x</body></html>")
    assert isinstance(doc.children[0], Comment)
    assert doc.root is not None
    assert doc.root.tag == "html"


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param("<p>hi</p>", "Document()", id="document"),
        pytest.param("<p>hi</p>", "Element('p')", id="element"),
        pytest.param("<p>hi</p>", "Text('hi')", id="text"),
        pytest.param("<!--note-->", "Comment('note')", id="comment"),
        pytest.param("<!DOCTYPE html>", "Doctype('html')", id="doctype"),
    ],
)
def test_repr(html: str, expected: str) -> None:
    doc = parse(html)
    node = next((n for n in doc.descendants if repr(n) == expected), doc)
    assert repr(node) == expected


def test_template_content_is_a_bare_node(find: Callable[[str, str], Element]) -> None:
    template = find("<template>inner</template>", "template")
    (content,) = template.children
    assert type(content) is Node
    assert repr(content) == "Node()"
    assert content.text == "inner"


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: parse(123), id="parse"),  # ty: ignore[invalid-argument-type]  # not str or bytes-like
        pytest.param(lambda: parse_fragment(b"x"), id="parse_fragment"),  # ty: ignore[invalid-argument-type]  # non-str
    ],
)
def test_entry_points_reject_non_str(call: Callable[[], object]) -> None:
    with pytest.raises(TypeError):
        call()


@pytest.mark.parametrize(
    ("html", "context", "tag", "child_tags", "text"),
    [
        pytest.param("<td>a<td>b", "tr", "tr", ["td", "td"], "ab", id="table-row-context"),
        pytest.param("<b>x</b>", "div", "div", ["b"], "x", id="default-div-context"),
        pytest.param("<path/>", "svg", "svg", ["path"], "", id="svg-context"),
        pytest.param("stray", "tbody", "tbody", [], "stray", id="fosters-stray-text-without-table"),
    ],
)
def test_parse_fragment(html: str, context: str, tag: str, child_tags: list[str], text: str) -> None:
    root = parse_fragment(html, context)
    assert isinstance(root, Element)
    assert root.tag == tag
    assert [c.tag for c in root if isinstance(c, Element)] == child_tags
    assert root.text == text


def test_parse_fragment_context_is_keyword() -> None:
    assert parse_fragment("<col>", context="colgroup").tag == "colgroup"


def test_equality_is_node_identity() -> None:
    doc = parse("<p>hi</p>")
    html, same = doc.find("html"), doc.find("html")  # distinct wrappers of one node
    assert html == same
    assert html != doc.find("body")
    assert (html == "html") is False  # a non-node is never equal
    assert (html != "html") is True


def test_ordering_is_unsupported() -> None:
    doc = parse("<p>hi</p>")
    left, right = doc.root, doc.root
    assert left is not None
    assert right is not None
    with pytest.raises(TypeError):
        _ = left < right  # ty: ignore[unsupported-operator]  # nodes are unordered on purpose


def test_hashable_by_identity() -> None:
    doc = parse("<p>hi</p>")
    seen = {doc.root, doc.find("html"), doc.find("p")}
    assert len(seen) == 2


def test_subtree_outlives_its_document(find: Callable[[str, str], Element]) -> None:
    paragraph = find("<div><p>kept</p></div>", "p")
    gc.collect()
    assert paragraph.text == "kept"


@pytest.mark.parametrize("cls", [Node, Element, Text, Comment, Doctype, Document])
def test_types_are_not_constructible(cls: type) -> None:
    with pytest.raises(TypeError):
        cls()


def test_namespace_values() -> None:
    assert {n.value for n in Namespace} == {"html", "svg", "math"}
