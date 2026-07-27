"""CSS selectors over a parse_xml() document: tag and attribute names are case-sensitive."""

from __future__ import annotations

import pytest

from turbohtml import Element, parse_xml

_DOC = '<Root><Child Attr="v" class="c"/><child/><div/><DIV/><Wide data-K="1"/></Root>'


def _root(markup: str) -> Element:
    root = parse_xml(markup).root
    assert isinstance(root, Element)
    return root


def _sel(selector: str) -> list[str]:
    return [element.tag for element in _root(_DOC).select(selector)]


@pytest.mark.parametrize(
    ("selector", "tags"),
    [
        pytest.param("Child", ["Child"], id="type-exact"),
        pytest.param("child", ["child"], id="type-lower"),
        pytest.param("div", ["div"], id="builtin-name-exact"),
        pytest.param("DIV", ["DIV"], id="builtin-name-upper"),
        pytest.param("Foo", [], id="type-absent"),
        pytest.param("[Attr]", ["Child"], id="attr-exact"),
        pytest.param("[attr]", [], id="attr-wrong-case"),
        pytest.param("[Attr=v]", ["Child"], id="attr-value-exact"),
        pytest.param("[attr=v]", [], id="attr-value-wrong-case"),
        pytest.param("[data-K]", ["Wide"], id="attr-mixed-case"),
        pytest.param("[data-k]", [], id="attr-mixed-case-wrong"),
    ],
)
def test_xml_selectors_are_case_sensitive(selector: str, tags: list[str]) -> None:
    assert _sel(selector) == tags


def test_xml_matches_is_case_sensitive() -> None:
    child = _root("<Root><child/></Root>").select_one("child")
    assert child is not None
    assert child.matches("child")
    assert not child.matches("Child")


def test_xml_builtin_named_element_matches_only_its_spelling() -> None:
    root = _root("<Root><Table/></Root>")
    assert [element.tag for element in root.select("Table")] == ["Table"]
    assert root.select("table") == []
