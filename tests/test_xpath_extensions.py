"""User extension functions via ``extensions=``, like lxml.

A custom function is registered under a ``(namespace, name)`` key and called as
``name(...)`` (the un-namespaced ``(None, name)`` form, which needs no namespace
mapping). It receives a context whose ``context_node`` is the current element,
then the evaluated arguments: a node-set arrives as a list, a string/number/bool
as the matching Python scalar. The return must be a str, number, or bool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import turbohtml
from turbohtml import Element

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import SimpleNamespace

HTML = "<html><body><a href='/x'>one</a><a href='/y'>two</a></body></html>"


def count_nodes(_context: SimpleNamespace, nodes: list[object]) -> float:
    return float(len(nodes))


def shout(_context: SimpleNamespace, text: str) -> str:
    return text.upper()


def echo(_context: SimpleNamespace, value: float | bool) -> float | bool:  # noqa: FBT001  # positional by convention
    return value


def context_tag(context: SimpleNamespace) -> str:
    return context.context_node.tag


EXTENSIONS: dict[tuple[str | None, str], Callable[..., str | float | bool]] = {
    (None, "count_nodes"): count_nodes,
    (None, "shout"): shout,
    (None, "echo"): echo,
    (None, "context_tag"): context_tag,
}


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


def test_nodeset_argument_arrives_as_a_list(doc: turbohtml.Node) -> None:
    assert doc.xpath("count_nodes(//a)", extensions=EXTENSIONS) == pytest.approx(2.0)


def test_string_argument_and_string_return(doc: turbohtml.Node) -> None:
    assert doc.xpath("shout(string(//a[1]/@href))", extensions=EXTENSIONS) == "/X"


def test_number_argument_round_trips(doc: turbohtml.Node) -> None:
    assert doc.xpath("echo(40 + 2)", extensions=EXTENSIONS) == pytest.approx(42.0)


def test_boolean_argument_round_trips(doc: turbohtml.Node) -> None:
    assert doc.xpath("echo(true())", extensions=EXTENSIONS) is True


def test_context_node_is_the_current_element(doc: turbohtml.Node) -> None:
    nodes = [n for n in doc.xpath("//a[context_tag()='a']", extensions=EXTENSIONS) if isinstance(n, Element)]
    assert [n.text for n in nodes] == ["one", "two"]


def test_extension_in_a_predicate(doc: turbohtml.Node) -> None:
    nodes = [n for n in doc.xpath("//a[count_nodes(.) = 1]", extensions=EXTENSIONS) if isinstance(n, Element)]
    assert [n.text for n in nodes] == ["one", "two"]


def test_extension_alongside_a_variable(doc: turbohtml.Node) -> None:
    assert doc.xpath("shout($s)", s="hi", extensions=EXTENSIONS) == "HI"


def test_extension_through_xpath_one(doc: turbohtml.Node) -> None:
    assert doc.xpath_one("count_nodes(//a)", extensions=EXTENSIONS) == pytest.approx(2.0)


def test_unknown_function_with_extensions_is_unimplemented(doc: turbohtml.Node) -> None:
    with pytest.raises(NotImplementedError):
        doc.xpath("nope()", extensions=EXTENSIONS)


def test_unknown_function_without_extensions_is_unimplemented(doc: turbohtml.Node) -> None:
    with pytest.raises(NotImplementedError):
        doc.xpath("count_nodes(//a)")


def test_empty_extensions_dict_registers_nothing(doc: turbohtml.Node) -> None:
    with pytest.raises(NotImplementedError):
        doc.xpath("count_nodes(//a)", extensions={})


def test_none_extensions_is_the_same_as_omitting_it(doc: turbohtml.Node) -> None:
    assert isinstance(doc.xpath("//a", extensions=None), list)


def test_extension_that_raises_propagates(doc: turbohtml.Node) -> None:
    with pytest.raises(ZeroDivisionError):
        doc.xpath("boom()", extensions={(None, "boom"): lambda _context: 1 / 0})


def test_extension_returning_a_non_scalar_is_a_type_error(doc: turbohtml.Node) -> None:
    with pytest.raises(TypeError, match="extension result must be"):
        doc.xpath("bad()", extensions={(None, "bad"): lambda _context: [1, 2]})  # ty: ignore[invalid-argument-type]  # non-scalar return on purpose


def test_extensions_must_be_a_dict(doc: turbohtml.Node) -> None:
    with pytest.raises(TypeError, match="extensions must be a dict"):
        doc.xpath("//a", extensions="not a dict")  # ty: ignore[invalid-argument-type]  # wrong type on purpose


def test_extension_receiving_an_element_from_a_nodeset(doc: turbohtml.Node) -> None:
    # the marshaled node-set holds Element objects the extension can navigate.
    def first_text(_context: SimpleNamespace, nodes: list[Element]) -> str:
        return nodes[0].text

    assert doc.xpath("first_text(//a)", extensions={(None, "first_text"): first_text}) == "one"
