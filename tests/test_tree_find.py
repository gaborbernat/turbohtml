"""find()/find_all(): the filter grammar (str/regex/bool/callable/list), class_, axes, and limit."""

from __future__ import annotations

import re

import pytest

from turbohtml import Axis, Element, parse

# document order of elements: html, head, body, section, h2, p, p, a
_DOC = '<section><h2 id="t">T</h2><p class="lead big">one</p><p class="big">two</p><a href="/x">l</a></section>'


def _tags(elements: list[Element]) -> list[str]:
    return [element.tag for element in elements]


def _el(result: Element | None) -> Element:
    assert result is not None
    return result


def _raise(_value: str | None) -> bool:
    raise ZeroDivisionError


# --- tag filter kinds ---


def test_tag_string_is_exact() -> None:
    assert _tags(parse(_DOC).find_all("p")) == ["p", "p"]


def test_tag_regex_searches() -> None:
    assert _tags(parse(_DOC).find_all(re.compile(r"^h"))) == ["html", "head", "h2"]


def test_tag_callable_receives_the_name() -> None:
    assert _tags(parse(_DOC).find_all(lambda name: name in {"h2", "a"})) == ["h2", "a"]


def test_tag_list_matches_any_member() -> None:
    assert _tags(parse(_DOC).find_all(["h2", "a"])) == ["h2", "a"]


def test_tag_true_matches_every_element() -> None:
    # tag is positional-only, so the bool filter must be passed positionally
    assert len(parse(_DOC).find_all(True)) == 8  # noqa: FBT003


# --- attribute filter kinds ---


def test_attr_exact_string() -> None:
    assert _el(parse(_DOC).find(id="t")).tag == "h2"


def test_attr_regex() -> None:
    assert _el(parse(_DOC).find(id=re.compile(r"^t$"))).tag == "h2"


def test_attr_true_is_presence() -> None:
    assert _tags(parse(_DOC).find_all(id=True)) == ["h2"]


def test_attr_false_is_absence() -> None:
    assert "a" not in _tags(parse(_DOC).find_all(href=False))  # only <a> carries href
    assert parse(_DOC).find("a", href=False) is None


def test_attr_callable_on_absent_value_gets_none() -> None:
    seen: list[str | None] = []
    parse("<div id=x><span></span></div>").find_all(id=lambda value: bool(seen.append(value)))
    assert None in seen  # the <span> has no id, so the callable saw None


# --- class_ is member-wise with a whole-value fallback ---


def test_class_matches_a_token() -> None:
    assert _tags(parse(_DOC).find_all(class_="big")) == ["p", "p"]


def test_class_matches_the_whole_value() -> None:
    assert _el(parse(_DOC).find(class_="lead big")).text == "one"


def test_class_regex_matches_a_token() -> None:
    assert _el(parse(_DOC).find(class_=re.compile(r"^lea"))).text == "one"


def test_class_true_is_presence() -> None:
    assert _tags(parse(_DOC).find_all(class_=True)) == ["p", "p"]


def test_class_false_is_absence() -> None:
    assert "p" not in _tags(parse(_DOC).find_all(class_=False))


def test_class_on_valueless_attribute() -> None:
    doc = parse("<div class>")
    assert doc.find("div", class_=True) == doc.find("div")  # present
    assert doc.find("div", class_="x") is None  # no tokens to match


def test_class_via_attrs_dict_is_whole_value_not_member() -> None:
    # the attrs dict treats class as an ordinary whole-string attribute
    assert _tags(parse(_DOC).find_all("p", attrs={"class": "big"})) == ["p"]


def test_class_token_scan_handles_surrounding_whitespace() -> None:
    # leading and trailing spaces around the tokens still resolve to ["a", "b"]
    assert _el(parse('<p class=" a b ">').find("p", class_="a")).tag == "p"
    assert parse('<p class=" a b ">').find("p", class_="c") is None


# --- valueless attributes ---


def test_filter_on_present_valueless_attribute() -> None:
    assert _el(parse("<input disabled>").find("input", disabled=True)).tag == "input"


def test_regex_on_valueless_attribute_does_not_match() -> None:
    assert parse("<input disabled>").find("input", disabled=re.compile(r"x")) is None


# --- axes ---


def test_axis_children() -> None:
    section = _el(parse(_DOC).find("section"))
    assert _tags(section.find_all("p", axis=Axis.CHILDREN)) == ["p", "p"]


def test_axis_ancestors() -> None:
    h2 = _el(parse(_DOC).find("h2"))
    assert _el(h2.find("section", axis=Axis.ANCESTORS)).tag == "section"


def test_axis_ancestors_walks_past_the_nearest() -> None:
    h2 = _el(parse(_DOC).find("h2"))
    assert _el(h2.find("body", axis=Axis.ANCESTORS)).tag == "body"


def test_axis_next_siblings() -> None:
    h2 = _el(parse(_DOC).find("h2"))
    assert _tags(h2.find_all(axis=Axis.NEXT_SIBLINGS)) == ["p", "p", "a"]


def test_axis_previous_siblings() -> None:
    link = _el(parse(_DOC).find("a"))
    assert _tags(link.find_all(axis=Axis.PREVIOUS_SIBLINGS)) == ["p", "p", "h2"]


def test_axis_following_skips_text_nodes() -> None:
    h2 = _el(parse(_DOC).find("h2"))
    assert _el(h2.find("a", axis=Axis.FOLLOWING)).tag == "a"


def test_axis_preceding_excludes_ancestors() -> None:
    link = _el(parse(_DOC).find("a"))
    assert _el(link.find("h2", axis=Axis.PRECEDING)).tag == "h2"


# --- limit ---


@pytest.mark.parametrize(
    ("limit", "count"),
    [
        pytest.param(None, 2, id="none"),
        pytest.param(1, 1, id="one"),
        pytest.param(0, 0, id="zero"),
        pytest.param(-1, 2, id="negative-is-unlimited"),
    ],
)
def test_limit(limit: int | None, count: int) -> None:
    assert len(parse(_DOC).find_all("p", limit=limit)) == count


# --- dynamic (non-common) attribute names ---


def test_dynamic_attr_name() -> None:
    assert _el(parse('<div data-x="v">').find("div", attrs={"data-x": "v"})).tag == "div"


def test_dynamic_attr_name_unseen_in_tree_matches_nothing() -> None:
    assert parse("<div>").find_all("div", attrs={"data-missing": True}) == []


def test_empty_attr_name_matches_nothing() -> None:
    assert parse("<div>").find_all("div", attrs={"": True}) == []


# --- list filter propagates an error from a member ---


def test_list_filter_propagates_callable_error() -> None:
    with pytest.raises(ZeroDivisionError):
        parse("<p>").find(id=[re.compile(r"z"), _raise])


# --- argument errors ---


def test_bad_axis_type() -> None:
    with pytest.raises(TypeError):
        # axis must be an Axis member; a str is rejected at runtime
        parse(_DOC).find("p", axis="descendants")  # ty: ignore[invalid-argument-type]


def test_bad_limit_type() -> None:
    with pytest.raises(TypeError):
        # limit must be an int or None; a str is rejected at runtime
        parse(_DOC).find_all("p", limit="lots")  # ty: ignore[invalid-argument-type]


def test_attrs_must_be_a_dict() -> None:
    with pytest.raises(TypeError):
        # attrs must be a Mapping; a list is rejected at runtime
        parse(_DOC).find("p", attrs=["id"])  # ty: ignore[invalid-argument-type]


def test_attr_name_must_be_a_str() -> None:
    with pytest.raises(TypeError):
        # a non-str attribute name is rejected at runtime
        parse(_DOC).find("p", attrs={1: "x"})  # ty: ignore[invalid-argument-type]


def test_unknown_filter_type() -> None:
    with pytest.raises(TypeError):
        # an int is not a valid filter; the type is rejected at runtime
        parse("<p>").find(id=123)  # ty: ignore[invalid-argument-type]


def test_callable_error_propagates() -> None:
    with pytest.raises(ZeroDivisionError):
        parse("<p>").find(id=_raise)
