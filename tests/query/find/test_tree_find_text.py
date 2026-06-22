"""find()/find_all(text=...): the text predicate over an element's collected text."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from turbohtml import Axis, Element, parse

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeAlias

    TextFilter: TypeAlias = "str | re.Pattern[str] | Callable[[str | None], bool]"

_DOC = (
    "<section>"
    '<button class="buy">Add to cart</button>'
    "<p>Price: $19</p>"
    '<span data-sku="x">SKU-7788</span>'
    "<button>Cancel</button>"
    "</section>"
)


def _tags(elements: list[Element]) -> list[str]:
    return [element.tag for element in elements]


def _el(result: Element | None) -> Element:
    assert result is not None
    return result


def _raise_text(_value: str | None) -> bool:
    raise ZeroDivisionError


def _starts_with_sku(value: str | None) -> bool:
    return value is not None and value.startswith("SKU")


@pytest.mark.parametrize(
    ("text_filter", "tags"),
    [
        pytest.param("Add to cart", ["button"], id="string-is-exact-collected-text"),
        pytest.param(re.compile(r"\$\d+"), ["p"], id="regex-searches"),
        pytest.param(_starts_with_sku, ["span"], id="callable-receives-text"),
        pytest.param("Cancel", ["button"], id="string-matches-second-button"),
        pytest.param("nope", [], id="string-no-match"),
    ],
)
def test_text_predicate_kinds(text_filter: TextFilter, tags: list[str]) -> None:
    # search the section's descendants, so the html/body/section wrappers (whose collected
    # text is every child concatenated) do not also match
    section = _el(parse(_DOC).find("section"))
    assert _tags(section.find_all(text=text_filter)) == tags


def test_text_is_the_whole_collected_text_not_a_substring() -> None:
    section = _el(parse("<section><p>Add to cart now</p><p>Add to cart</p></section>").find("section"))
    assert _tags(section.find_all(text="Add to cart")) == ["p"]  # a str filter is the full collected text
    assert _tags(section.find_all(text="Add to cart now")) == ["p"]


def test_text_collects_nested_descendants() -> None:
    section = _el(parse("<section><p>Buy <b>now</b></p></section>").find("section"))
    assert _tags(section.find_all(text="Buy now")) == ["p"]  # <p> collects "Buy " + "now"
    assert _tags(section.find_all(text="now")) == ["b"]  # only <b> collects exactly "now"


def test_text_matches_an_ancestor_whose_collected_text_equals_the_target() -> None:
    # the collected text is the whole subtree, so a wrapper with one matching child matches too
    doc = parse("<div><p>solo</p></div>")
    assert _tags(_el(doc.find("body")).find_all(text="solo")) == ["div", "p"]


def test_find_returns_first_match() -> None:
    section = _el(parse(_DOC).find("section"))
    assert _el(section.find(text=re.compile(r"\$"))).tag == "p"


def test_find_no_match_returns_none() -> None:
    assert parse(_DOC).find(text="missing") is None


def test_find_all_no_match_returns_empty_list() -> None:
    assert parse(_DOC).find_all(text="missing") == []


def test_no_structural_candidate_short_circuits() -> None:
    # a known tag absent from the tree leaves zero candidates before any text is gathered
    doc = parse("<p>go</p>")
    assert doc.find_all("table", text="go") == []
    assert doc.find("table", text="go") is None


def test_text_composes_with_tag_filter() -> None:
    # only the <button> whose text matches, not the <p> that also mentions the price
    doc = parse("<button>Add to cart</button><p>Add to cart</p>")
    assert _tags(doc.find_all("button", text="Add to cart")) == ["button"]


def test_text_composes_with_regex_tag_filter() -> None:
    doc = parse("<button>go</button><bdo>go</bdo><div>go</div>")
    assert _tags(doc.find_all(re.compile(r"^b"), text="go")) == ["button", "bdo"]


def test_text_composes_with_custom_element_tag() -> None:
    doc = parse("<my-widget>go</my-widget><my-widget>stop</my-widget>")
    assert _tags(doc.find_all("my-widget", text="go")) == ["my-widget"]


def test_text_composes_with_class_filter() -> None:
    doc = parse('<button class="buy">go</button><button>go</button>')
    assert _tags(doc.find_all(class_="buy", text="go")) == ["button"]


def test_text_composes_with_attribute_filter() -> None:
    doc = parse('<span data-sku="x">go</span><span>go</span>')
    assert _tags(doc.find_all(text="go", attrs={"data-sku": "x"})) == ["span"]


def test_text_attribute_filter_via_kwargs_is_reserved() -> None:
    # a literal "text" attribute is filtered through attrs=, since text= is the predicate
    doc = parse('<span text="hi">go</span><span>go</span>')
    assert _tags(doc.find_all(text="go")) == ["span", "span"]  # both spans collect "go"
    assert _tags(doc.find_all(text="go", attrs={"text": "hi"})) == ["span"]


@pytest.mark.parametrize(
    ("limit", "count"),
    [
        pytest.param(None, 3, id="none-is-unlimited"),
        pytest.param(0, 0, id="zero-yields-nothing"),
        pytest.param(2, 2, id="caps-results"),
    ],
)
def test_find_all_limit(limit: int | None, count: int) -> None:
    doc = parse("<p>go</p><p>go</p><p>go</p>")
    assert len(doc.find_all(text="go", limit=limit)) == count


def test_text_on_children_axis() -> None:
    doc = parse("<section><p>go</p><div><span>x</span></div></section>")
    section = _el(doc.find("section"))
    assert _tags(section.find_all(text="go", axis=Axis.CHILDREN)) == ["p"]  # the <div> child collects "x"
    assert _tags(section.find_all(text="x")) == ["div", "span"]  # <div> and its <span> both collect "x"


def test_text_callable_error_propagates() -> None:
    with pytest.raises(ZeroDivisionError):
        parse(_DOC).find_all(text=_raise_text)


def test_text_callable_error_propagates_on_find() -> None:
    with pytest.raises(ZeroDivisionError):
        parse(_DOC).find(text=_raise_text)


def test_structural_callable_error_propagates_with_text() -> None:
    # the structural filter raises during the snapshot pass, before the text predicate runs
    def _boom(_value: str | None) -> bool:
        raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        parse(_DOC).find_all(text="go", id=_boom)


def test_structural_callable_error_propagates_with_text_on_find() -> None:
    def _boom(_value: str | None) -> bool:
        raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        parse(_DOC).find(text="go", id=_boom)


def test_text_invalid_type_raises_type_error() -> None:
    with pytest.raises(TypeError):
        parse("<p>go</p>").find_all(text=123)  # ty: ignore[invalid-argument-type]


def test_text_only_matches_elements_not_text_nodes() -> None:
    # text nodes appear on the descendants walk but never match the element-only predicate
    doc = parse("<section>loose<p>go</p></section>")
    assert _tags(doc.find_all(text="go")) == ["p"]
