"""``$name`` variable references bound through keyword arguments, like lxml/parsel.

A keyword argument binds a variable the expression can reference: ``str`` becomes a
string, ``int``/``float`` a number, ``bool`` a boolean, and an :class:`~turbohtml.Element`
or an iterable of elements a node-set, so a prior result feeds a later expression
(``doc.xpath("$rows/td", rows=doc.xpath("//tr"))``). A node-set variable joins path
steps, ``count()``, unions, and predicates like any other node-set, ordered in document
order with duplicates dropped on reference. Referencing an unbound name raises
``ValueError``; a node from a different tree raises ``ValueError``; an unsupported value
type raises ``TypeError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import turbohtml
from turbohtml import Element

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

HTML = (
    "<html><body>"
    "<table><tr id='r1'><td>a</td><td>b</td></tr><tr id='r2'><td>c</td></tr></table>"
    "<p id='a'>one</p><p id='b'>two</p><p id='c'>three</p>"
    "</body></html>"
)


def tags(result: list[Element | str]) -> list[str]:
    return [node.tag if isinstance(node, Element) else node for node in result]


def ids(result: list[Element | str]) -> list[str | None]:
    return [node.attr("id") for node in result if isinstance(node, Element)]


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


@pytest.mark.parametrize(
    ("expr", "kwargs", "expected"),
    [
        pytest.param("//p[@id=$want]", {"want": "b"}, ["p"], id="string-in-predicate"),
        pytest.param("//p[position()=$n]", {"n": 2}, ["p"], id="int-in-predicate"),
        pytest.param("//p[$keep]", {"keep": True}, ["p", "p", "p"], id="bool-true"),
        pytest.param("//p[$keep]", {"keep": False}, [], id="bool-false"),
        pytest.param("//p[@id=$a or @id=$b]", {"a": "a", "b": "c"}, ["p", "p"], id="two-variables"),
    ],
)
def test_variable_node_set(
    doc: turbohtml.Node, expr: str, kwargs: dict[str, str | int | float | bool], expected: list[str]
) -> None:
    assert tags(doc.xpath(expr, **kwargs)) == expected  # ty: ignore[invalid-argument-type]  # variables unpacked as a dict


@pytest.mark.parametrize(
    ("expr", "kwargs", "expected"),
    [
        pytest.param("$s", {"s": "hi"}, "hi", id="string-value"),
        pytest.param("$s", {"s": ""}, "", id="empty-string-value"),
        pytest.param("$n", {"n": 7}, 7.0, id="int-value"),
        pytest.param("$n", {"n": 2.5}, 2.5, id="float-value"),
        pytest.param("$n", {"n": -1}, -1.0, id="minus-one-is-a-value-not-an-error"),
        pytest.param("$b", {"b": True}, True, id="bool-value"),
        pytest.param("$a + $b", {"a": 2, "b": 3}, 5.0, id="arithmetic"),
        pytest.param("count(//p) = $n", {"n": 3}, True, id="compared-to-count"),
    ],
)
def test_variable_scalar(
    doc: turbohtml.Node, expr: str, kwargs: dict[str, str | int | float | bool], expected: object
) -> None:
    assert doc.xpath(expr, **kwargs) == expected  # ty: ignore[invalid-argument-type]  # variables unpacked as a dict


def test_unbound_variable_without_any_binding(doc: turbohtml.Node) -> None:
    with pytest.raises(ValueError, match="unbound variable"):
        doc.xpath("$missing")


def test_unbound_variable_with_other_bindings_present_length_differs(doc: turbohtml.Node) -> None:
    with pytest.raises(ValueError, match="unbound variable"):
        doc.xpath("$missing", other="x")


def test_unbound_variable_same_length_different_name(doc: turbohtml.Node) -> None:
    with pytest.raises(ValueError, match="unbound variable"):
        doc.xpath("$abc", xyz="v")


def test_unsupported_variable_type(doc: turbohtml.Node) -> None:
    with pytest.raises(TypeError, match="an iterable of elements"):
        doc.xpath("//p[@id=$x]", x=[1, 2])  # ty: ignore[invalid-argument-type]  # ints are not elements


def test_unsupported_type_after_a_valid_binding_frees_the_partial(doc: turbohtml.Node) -> None:
    with pytest.raises(TypeError, match="an iterable of elements"):
        doc.xpath("$good", good="x", bad=[1])  # ty: ignore[invalid-argument-type]  # the second binding is unsupported


def test_integer_too_large_for_a_double(doc: turbohtml.Node) -> None:
    with pytest.raises(OverflowError):
        doc.xpath("$n", n=10**400)


def test_missing_expression_argument(doc: turbohtml.Node) -> None:
    with pytest.raises(TypeError):
        doc.xpath()  # ty: ignore[missing-argument]  # the no-argument path raises at the C boundary


def test_variable_through_xpath_iter(doc: turbohtml.Node) -> None:
    items = [node for node in doc.xpath_iter("//p[@id=$w]", w="a") if isinstance(node, Element)]
    assert [node.tag for node in items] == ["p"]


def test_variable_through_xpath_one(doc: turbohtml.Node) -> None:
    result = doc.xpath_one("//p[@id=$w]", w="c")
    assert isinstance(result, Element)
    assert result.text == "three"


def query(node: turbohtml.Node, expression: str) -> list[Element]:
    return [item for item in node.xpath(expression) if isinstance(item, Element)]


def reversed_with_duplicate(node: turbohtml.Node) -> list[Element]:
    paragraphs = query(node, "//p")
    return [paragraphs[1], paragraphs[0], paragraphs[1]]


@pytest.mark.parametrize(
    ("expr", "make_kwargs", "expected_ids"),
    [
        pytest.param(
            "$start//tr",
            lambda document: {"start": query(document, "//table")[0]},
            ["r1", "r2"],
            id="single-element-feeds-a-descendant-step",
        ),
        pytest.param(
            "$rows",
            lambda document: {"rows": query(document, "//tr")},
            ["r1", "r2"],
            id="node-set-returned-directly-as-a-list",
        ),
        pytest.param(
            "$rows | //p",
            lambda document: {"rows": query(document, "//tr")},
            ["r1", "r2", "a", "b", "c"],
            id="union-with-a-node-set",
        ),
        pytest.param(
            "//tr[. = $first]",
            lambda document: {"first": query(document, "//tr[@id='r1']")},
            ["r1"],
            id="predicate-references-a-node-set",
        ),
        pytest.param(
            "$items",
            lambda document: {"items": reversed_with_duplicate(document)},
            ["a", "b"],
            id="normalized-to-document-order-without-duplicates",
        ),
        pytest.param(
            "$items",
            lambda document: {"items": query(document, "//section")},
            [],
            id="empty-node-set",
        ),
    ],
)
def test_node_set_variable_resolves_to_elements(
    doc: turbohtml.Node,
    expr: str,
    make_kwargs: Callable[[turbohtml.Node], dict[str, Element | list[Element]]],
    expected_ids: list[str],
) -> None:
    assert ids(doc.xpath(expr, **make_kwargs(doc))) == expected_ids  # ty: ignore[invalid-argument-type]  # variables unpacked as a dict


def test_node_set_variable_feeds_a_path_step(doc: turbohtml.Node) -> None:
    assert tags(doc.xpath("$rows/td", rows=query(doc, "//tr"))) == ["td", "td", "td"]


@pytest.mark.parametrize(
    ("query_expr", "expected"),
    [
        pytest.param("//p", 3.0, id="count-over-a-populated-node-set"),
        pytest.param("//section", 0.0, id="count-over-an-empty-node-set"),
    ],
)
def test_count_over_a_node_set_variable(doc: turbohtml.Node, query_expr: str, expected: float) -> None:
    assert doc.xpath("count($items)", items=query(doc, query_expr)) == pytest.approx(expected)


def test_node_set_variable_through_xpath_iter(doc: turbohtml.Node) -> None:
    cells = [node for node in doc.xpath_iter("$rows/td", rows=query(doc, "//tr")) if isinstance(node, Element)]
    assert [node.tag for node in cells] == ["td", "td", "td"]


def test_node_set_variable_through_xpath_one(doc: turbohtml.Node) -> None:
    first = doc.xpath_one("$rows", rows=query(doc, "//tr"))
    assert isinstance(first, Element)
    assert first.attr("id") == "r1"


def foreign_nodes() -> list[Element]:
    other = turbohtml.parse("<html><body><span id='x'>elsewhere</span></body></html>")
    return query(other, "//span")


def yield_then_raise(node: turbohtml.Node) -> Iterator[Element]:
    yield query(node, "//p")[0]
    msg = "boom"
    raise RuntimeError(msg)


@pytest.mark.parametrize(
    ("make_items", "exc", "match"),
    [
        pytest.param(lambda _document: foreign_nodes(), ValueError, "different tree", id="node-from-a-different-tree"),
        pytest.param(yield_then_raise, RuntimeError, "boom", id="iterable-raises-partway"),
    ],
)
def test_node_set_variable_rejects_bad_node_sets(
    doc: turbohtml.Node,
    make_items: Callable[[turbohtml.Node], Iterable[Element]],
    exc: type[Exception],
    match: str,
) -> None:
    with pytest.raises(exc, match=match):
        doc.xpath("$items", items=make_items(doc))


@pytest.mark.parametrize(
    "make_items",
    [
        pytest.param(
            lambda document: [query(document, "//p")[0], "not-an-element"], id="non-element-inside-an-iterable"
        ),
        pytest.param(lambda _document: None, id="non-iterable-non-scalar-value"),
    ],
)
def test_node_set_variable_rejects_unsupported_values(
    doc: turbohtml.Node, make_items: Callable[[turbohtml.Node], object]
) -> None:
    with pytest.raises(TypeError, match="an iterable of elements"):
        doc.xpath("$items", items=make_items(doc))  # ty: ignore[invalid-argument-type]  # deliberately wrong value type
