"""``$name`` variable references bound through keyword arguments, like lxml/parsel.

A keyword argument binds a variable the expression can reference: ``str`` becomes a
string, ``int``/``float`` a number, ``bool`` a boolean. Referencing an unbound name
raises ``ValueError``; an unsupported value type raises ``TypeError``.
"""

from __future__ import annotations

import pytest

import turbohtml
from turbohtml import Element

HTML = "<html><body><p id='a'>one</p><p id='b'>two</p><p id='c'>three</p></body></html>"


def tags(result: list[Element | str]) -> list[str]:
    return [node.tag if isinstance(node, Element) else node for node in result]


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
    with pytest.raises(TypeError, match="str, int, float, or bool"):
        doc.xpath("//p[@id=$x]", x=[1, 2])  # ty: ignore[invalid-argument-type]  # list is an unsupported var type


def test_unsupported_type_after_a_valid_binding_frees_the_partial(doc: turbohtml.Node) -> None:
    with pytest.raises(TypeError, match="str, int, float, or bool"):
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
