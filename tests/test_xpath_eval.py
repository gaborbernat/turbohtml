"""Evaluation of XPath location paths through ``Node.xpath`` / ``Node.xpath_one``.

Phase 2 implements location paths (the forward and reverse structural axes, name/
``*``/``node()``/``text()``/``comment()`` tests, attribute access) returning node-sets;
predicates, operators, functions, unions, and filter expressions raise
``NotImplementedError`` until later phases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import turbohtml
from turbohtml import Element

if TYPE_CHECKING:
    from collections.abc import Iterable

HTML = (
    "<!doctype html><html><head><title>T</title></head><body>"
    '<div id="d1" class="box"><p>a</p><p class="hi">b</p></div>'
    '<div id="d2"><span>s1</span><span>s2</span></div>'
    "<ul><li>1</li><li>2</li></ul>"
    '<a href="/x">L1</a><a href="/y" rel="next">L2</a>'
    "<input disabled>"
    '<my-widget data-k="v">w</my-widget>'
    "<!-- cmt --></body></html>"
)


def tags(result: Iterable[object]) -> list[str]:
    return [node.tag for node in result if isinstance(node, Element)]


def one(node: turbohtml.Node, expr: str) -> Element:
    """The single Element an expression is expected to select."""
    result = node.xpath_one(expr)
    assert isinstance(result, Element)
    return result


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


def test_descendant_name(doc: turbohtml.Node) -> None:
    assert tags(doc.xpath("//p")) == ["p", "p"]


def test_descendant_wildcard_is_elements_only(doc: turbohtml.Node) -> None:
    assert tags(doc.xpath("//div/*")) == ["p", "p", "span", "span"]


def test_absolute_path(doc: turbohtml.Node) -> None:
    assert tags(doc.xpath("/html/body/div")) == ["div", "div"]


def test_root_node(doc: turbohtml.Node) -> None:
    assert doc.xpath("/") == [doc]


def test_attribute_values(doc: turbohtml.Node) -> None:
    assert doc.xpath("//a/@href") == ["/x", "/y"]
    assert doc.xpath("//a/@rel") == ["next"]
    assert doc.xpath("//p/@class") == ["hi"]


def test_attribute_wildcard(doc: turbohtml.Node) -> None:
    assert one(doc, "//div").xpath("@*") == ["d1", "box"]


def test_attribute_node_test_matches_all(doc: turbohtml.Node) -> None:
    assert one(doc, "//div").xpath("attribute::node()") == ["d1", "box"]
    assert one(doc, "//div").xpath("attribute::text()") == []


def test_valueless_attribute(doc: turbohtml.Node) -> None:
    assert doc.xpath("//input/@disabled") == [""]


def test_unicode_and_overlong_attribute_names_match_nothing(doc: turbohtml.Node) -> None:
    assert doc.xpath("//a/@café") == []
    assert doc.xpath("//a/@" + "z" * 200) == []


def test_step_after_attribute_yields_nothing(doc: turbohtml.Node) -> None:
    assert doc.xpath("//a/@href/x") == []


def test_text_nodes(doc: turbohtml.Node) -> None:
    assert doc.xpath("//title/text()") == ["T"]
    assert one(doc, "//title").xpath("node()") == ["T"]


def test_comment(doc: turbohtml.Node) -> None:
    assert len(doc.xpath("//comment()")) == 1


def test_processing_instruction_absent(doc: turbohtml.Node) -> None:
    assert doc.xpath("//processing-instruction()") == []


def test_unknown_element_matches_by_name(doc: turbohtml.Node) -> None:
    assert tags(doc.xpath("//my-widget")) == ["my-widget"]
    assert doc.xpath("//my-widget/@data-k") == ["v"]


def test_unknown_element_name_mismatch(doc: turbohtml.Node) -> None:
    assert doc.xpath("//my-gadget") == []


def test_unicode_and_overlong_names_match_nothing(doc: turbohtml.Node) -> None:
    assert doc.xpath("//café") == []
    assert doc.xpath("//" + "a" * 80) == []


def test_self_axis(doc: turbohtml.Node) -> None:
    p = one(doc, "//p")
    assert tags(p.xpath("self::p")) == ["p"]
    assert p.xpath("self::div") == []


def test_parent_axis(doc: turbohtml.Node) -> None:
    assert tags(one(doc, "//p").xpath("..")) == ["div"]
    assert one(doc, "//html").xpath("..") == [doc]
    assert doc.xpath("..") == []  # the document node has no parent
    assert doc.xpath("//p/parent::span") == []  # parent exists but fails the name test


def test_ancestor_axes_are_document_ordered(doc: turbohtml.Node) -> None:
    li = one(doc, "//li")
    assert tags(li.xpath("ancestor::*")) == ["html", "body", "ul"]
    assert tags(li.xpath("ancestor-or-self::*")) == ["html", "body", "ul", "li"]


def test_descendant_axis(doc: turbohtml.Node) -> None:
    assert tags(doc.xpath("//body/descendant::span")) == ["span", "span"]


def test_following_and_preceding_sibling(doc: turbohtml.Node) -> None:
    assert tags(one(doc, "//div").xpath("following-sibling::div")) == ["div"]
    assert tags(one(doc, "//ul").xpath("preceding-sibling::div")) == ["div", "div"]


def test_results_are_deduplicated(doc: turbohtml.Node) -> None:
    # both spans share the same ancestor div, which must appear once
    assert tags(doc.xpath("//span/ancestor::div")) == ["div"]


def test_context_relative(doc: turbohtml.Node) -> None:
    body = one(doc, "//body")
    assert tags(body.xpath("div")) == ["div", "div"]
    assert tags(body.xpath(".//span")) == ["span", "span"]


def test_xpath_one_returns_first_or_none(doc: turbohtml.Node) -> None:
    assert one(doc, "//a").tag == "a"
    assert doc.xpath_one("//a/@href") == "/x"
    assert doc.xpath_one("//zzz") is None


def test_xpath_iter_yields_results(doc: turbohtml.Node) -> None:
    iterator = doc.xpath_iter("//p")
    assert iter(iterator) is iterator
    assert tags(iterator) == ["p", "p"]


def test_xpath_iter_supports_partial_consumption(doc: turbohtml.Node) -> None:
    iterator = doc.xpath_iter("//*")
    first = next(iterator)
    assert isinstance(first, Element)
    assert first.tag == "html"


def test_xpath_iter_propagates_errors(doc: turbohtml.Node) -> None:
    with pytest.raises(NotImplementedError, match="following/preceding/namespace"):
        doc.xpath_iter("//following::x")
    with pytest.raises(TypeError, match="must be a str"):
        doc.xpath_iter(123)  # ty: ignore[invalid-argument-type]  # non-str exercises the TypeError path


@pytest.mark.parametrize(
    "expr",
    [
        pytest.param("//following::x", id="following"),
        pytest.param("//preceding::x", id="preceding"),
        pytest.param("//namespace::x", id="namespace"),
    ],
)
def test_unsupported_axes_raise(doc: turbohtml.Node, expr: str) -> None:
    with pytest.raises(NotImplementedError, match="following/preceding/namespace"):
        doc.xpath(expr)


def test_xpath_one_unsupported_raises(doc: turbohtml.Node) -> None:
    with pytest.raises(NotImplementedError, match="following/preceding/namespace"):
        doc.xpath_one("//following::x")


def test_invalid_expression_raises_value_error(doc: turbohtml.Node) -> None:
    with pytest.raises(ValueError, match="node test"):
        doc.xpath("//")


def test_non_string_argument(doc: turbohtml.Node) -> None:
    with pytest.raises(TypeError, match="must be a str"):
        doc.xpath(123)  # ty: ignore[invalid-argument-type]  # non-str exercises the TypeError path
    with pytest.raises(TypeError, match="must be a str"):
        doc.xpath_one(123)  # ty: ignore[invalid-argument-type]  # non-str exercises the TypeError path
