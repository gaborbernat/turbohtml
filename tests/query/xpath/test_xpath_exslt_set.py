"""EXSLT ``set:`` node-set functions built into the XPath engine.

libexslt gives lxml ``set:difference``, ``set:distinct``, ``set:intersection``,
``set:has-same-node``, ``set:leading``, and ``set:trailing``; turbohtml dispatches
the ``set:`` prefix in C without the caller registering a namespace.
"""

from __future__ import annotations

import pytest

import turbohtml
from turbohtml import Element

HTML = "<ul><li id='a' class='x'>1</li><li id='b' class='y'>2</li><li id='c' class='x'>3</li><li id='d'>1</li></ul>"


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


def ids(result: list[Element | str]) -> list[str]:
    collected: list[str] = []
    for node in result:
        assert isinstance(node, Element)
        value = node.attrs["id"]
        assert isinstance(value, str)
        collected.append(value)
    return collected


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("set:difference(//li, //li[@class='x'])", ["b", "d"], id="difference"),
        pytest.param("set:intersection(//li, //li[@class='x'])", ["a", "c"], id="intersection"),
        pytest.param("set:distinct(//li)", ["a", "b", "c"], id="distinct-by-string-value"),
        pytest.param("set:leading(//li, //li[@id='c'])", ["a", "b"], id="leading"),
        pytest.param("set:trailing(//li, //li[@id='c'])", ["d"], id="trailing"),
        pytest.param("set:leading(//li, //li[@id='gone'])", ["a", "b", "c", "d"], id="leading-empty-second"),
        pytest.param("set:trailing(//li, //li[@id='gone'])", ["a", "b", "c", "d"], id="trailing-empty-second"),
        pytest.param("set:leading(//li[@id='b'], //li[@id='a'])", [], id="leading-pivot-absent"),
        pytest.param("set:trailing(//li[@id='b'], //li[@id='a'])", [], id="trailing-pivot-absent"),
    ],
)
def test_set_nodeset_results(doc: turbohtml.Node, expr: str, expected: list[str]) -> None:
    assert ids(doc.xpath(expr)) == expected


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("set:has-same-node(//li[@class='x'], //li[@id='a'])", True, id="shares-first"),
        pytest.param("set:has-same-node(//li, //li[@id='c'])", True, id="shares-later"),
        pytest.param("set:has-same-node(//li[@id='a'], //li[@id='b'])", False, id="disjoint"),
    ],
)
def test_set_has_same_node(doc: turbohtml.Node, expr: str, *, expected: bool) -> None:
    assert doc.xpath(expr) is expected


@pytest.mark.parametrize(
    "expr",
    [
        pytest.param("set:difference('x', //li)", id="difference-non-nodeset"),
        pytest.param("set:has-same-node(//li, 'x')", id="has-same-node-non-nodeset"),
        pytest.param("set:distinct('x')", id="distinct-non-nodeset"),
    ],
)
def test_set_non_nodeset_argument_raises(doc: turbohtml.Node, expr: str) -> None:
    with pytest.raises(NotImplementedError, match="non-node-set"):
        doc.xpath(expr)


@pytest.fixture
def attr_doc() -> turbohtml.Node:
    # Several attributes on one element share a node but differ by attribute index, so
    # set operations over an attribute node-set exercise the same-node/different-attr path.
    return turbohtml.parse("<a id='1' class='c' data-x='y'>t</a>")


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("set:difference(//a/@*, //a/@class)", ["1", "y"], id="difference-attributes"),
        pytest.param("set:intersection(//a/@*, //a/@class)", ["c"], id="intersection-attributes"),
        pytest.param("set:leading(//a/@*, //a/@class)", ["1"], id="leading-attributes"),
        pytest.param("set:trailing(//a/@*, //a/@class)", ["y"], id="trailing-attributes"),
    ],
)
def test_set_over_attribute_nodesets(attr_doc: turbohtml.Node, expr: str, expected: list[str]) -> None:
    assert attr_doc.xpath(expr) == expected


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("set:has-same-node(//a/@id, //a/@*)", True, id="attr-member-present"),
        pytest.param("set:has-same-node(//a/@id, //a/@class)", False, id="attr-same-node-different-index"),
    ],
)
def test_set_has_same_node_attributes(attr_doc: turbohtml.Node, expr: str, *, expected: bool) -> None:
    assert attr_doc.xpath(expr) is expected


def test_set_distinct_mixed_lengths() -> None:
    # Values of differing lengths exercise the length comparison before the byte compare.
    doc = turbohtml.parse("<ul><li id='a'>1</li><li id='b'>22</li><li id='c'>1</li><li id='d'>22</li></ul>")
    assert ids(doc.xpath("set:distinct(//li)")) == ["a", "b"]
