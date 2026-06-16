"""find()/find_all(): the filter grammar (str/regex/bool/callable/list), class_, axes, and limit."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from turbohtml import Axis, Element, parse

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeAlias

    Filter: TypeAlias = "str | re.Pattern[str] | bool | Callable[[str | None], bool] | list[Filter]"

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


@pytest.mark.parametrize(
    ("tag_filter", "tags"),
    [
        pytest.param("p", ["p", "p"], id="string-exact"),
        pytest.param(re.compile(r"^h"), ["html", "head", "h2"], id="regex-search"),
        pytest.param(lambda name: name in {"h2", "a"}, ["h2", "a"], id="callable-receives-name"),
        pytest.param(["h2", "a"], ["h2", "a"], id="list-any-member"),
        pytest.param("\ud800", [], id="lone-surrogate-unencodable"),  # falls back to a str compare
        pytest.param("", [], id="empty-name"),  # no element has an empty name
    ],
)
def test_tag_filter(tag_filter: Filter, tags: list[str]) -> None:
    assert _tags(parse(_DOC).find_all(tag_filter)) == tags


def test_tag_string_is_case_sensitive() -> None:
    doc = parse("<div>x</div>")
    assert _tags(doc.find_all("div")) == ["div"]
    assert doc.find_all("DIV") == []  # tag names are lowercased, so the match is exact


def test_tag_matches_a_custom_element() -> None:
    html = "<my-widget>a</my-widget><other-thing>b</other-thing><my-widget>c</my-widget>"
    assert _tags(parse(html).find_all("my-widget")) == ["my-widget", "my-widget"]


def test_tag_true_matches_every_element() -> None:
    # tag is positional-only, so the bool filter must be passed positionally
    assert len(parse(_DOC).find_all(True)) == 8  # noqa: FBT003


def test_find_known_tag_absent_returns_none() -> None:
    assert parse(_DOC).find("table") is None  # fast path walks the subtree and finds nothing


def test_tag_with_attribute_filter_uses_the_general_path() -> None:
    # a tag plus any other filter leaves the tag-only fast path
    assert _tags(parse(_DOC).find_all("a", href="/x")) == ["a"]


@pytest.mark.parametrize(
    "class_filter", [pytest.param("big", id="string"), pytest.param(re.compile(r"big"), id="regex")]
)
def test_tag_with_class_filter_uses_the_general_path(class_filter: Filter) -> None:
    assert _tags(parse(_DOC).find_all("p", class_=class_filter)) == ["p", "p"]


# --- attribute filter kinds ---


@pytest.mark.parametrize(
    "id_filter", [pytest.param("t", id="exact-string"), pytest.param(re.compile(r"^t$"), id="regex")]
)
def test_attr_matches_h2(id_filter: Filter) -> None:
    assert _el(parse(_DOC).find(id=id_filter)).tag == "h2"


@pytest.mark.parametrize(
    "id_value",
    [pytest.param("x", id="same-length-different-content"), pytest.param("tt", id="different-length")],
)
def test_attr_string_near_miss(id_value: str) -> None:
    assert parse(_DOC).find(id=id_value) is None  # only the <h2> carries id="t"


@pytest.mark.parametrize(
    "id_filter",
    [
        # an absent attribute compares as None against each string member of the list
        pytest.param(["t", "u"], id="list-skips-absent-attribute"),
        pytest.param(True, id="true-is-presence"),
    ],
)
def test_attr_selects_h2(id_filter: Filter) -> None:
    assert _tags(parse(_DOC).find_all(id=id_filter)) == ["h2"]


def test_attr_false_is_absence() -> None:
    assert "a" not in _tags(parse(_DOC).find_all(href=False))  # only <a> carries href
    assert parse(_DOC).find("a", href=False) is None


def test_attr_callable_on_absent_value_gets_none() -> None:
    seen: list[str | None] = []
    parse("<div id=x><span></span></div>").find_all(id=lambda value: bool(seen.append(value)))
    assert None in seen  # the <span> has no id, so the callable saw None


# --- class_ is member-wise with a whole-value fallback ---


@pytest.mark.parametrize("class_filter", [pytest.param("big", id="token"), pytest.param(True, id="true-is-presence")])
def test_class_selects_paragraphs(class_filter: Filter) -> None:
    assert _tags(parse(_DOC).find_all(class_=class_filter)) == ["p", "p"]


@pytest.mark.parametrize(
    "class_filter",
    [
        pytest.param("lead big", id="whole-value"),
        # an anchored regex matches the leading "lead" token of "lead big"
        pytest.param(re.compile(r"^lea"), id="regex-token"),
    ],
)
def test_class_finds_the_lead(class_filter: Filter) -> None:
    assert _el(parse(_DOC).find(class_=class_filter)).text == "one"


def test_class_regex_matches_a_token_not_the_whole_value() -> None:
    # an anchored regex matches the "big" token of "lead big" but not the whole value
    doc = parse('<p class="lead big">x</p><p class="big">y</p>')
    assert len(doc.find_all("p", class_=re.compile(r"^big$"))) == 2


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


# --- filters that resolve to no match return None ---


@pytest.mark.parametrize(
    ("html", "class_filter"),
    [
        # a class value the same length as the filter but different content
        pytest.param('<p class="xyz">x</p>', "big", id="equal-length-mismatch"),
        # a non-matching regex walks every token of a whitespace-padded value,
        # including the trailing run that yields no token
        pytest.param('<p class=" a b ">x</p>', re.compile(r"zzz"), id="regex-no-token"),
    ],
)
def test_class_filter_no_match(html: str, class_filter: Filter) -> None:
    assert parse(html).find("p", class_=class_filter) is None


@pytest.mark.parametrize(
    "disabled_filter",
    [
        pytest.param("x", id="string"),
        pytest.param(re.compile(r"x"), id="regex"),
        # a valueless attribute compares as None against each list member
        pytest.param(["x", "y"], id="list"),
    ],
)
def test_filter_on_valueless_attribute_no_match(disabled_filter: Filter) -> None:
    assert parse("<input disabled>").find("input", disabled=disabled_filter) is None


def test_filter_on_present_valueless_attribute() -> None:
    assert _el(parse("<input disabled>").find("input", disabled=True)).tag == "input"


# --- axes ---


def test_axis_children() -> None:
    section = _el(parse(_DOC).find("section"))
    assert _tags(section.find_all("p", axis=Axis.CHILDREN)) == ["p", "p"]


@pytest.mark.parametrize(
    "target", [pytest.param("section", id="nearest"), pytest.param("body", id="walks-past-the-nearest")]
)
def test_axis_ancestors(target: str) -> None:
    h2 = _el(parse(_DOC).find("h2"))
    assert _el(h2.find(target, axis=Axis.ANCESTORS)).tag == target


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


def test_limit_on_the_general_path() -> None:
    # a bool filter uses the general matcher, where the limit applies the same way
    assert len(parse(_DOC).find_all(True, limit=1)) == 1  # noqa: FBT003


# --- dynamic (non-common) attribute names ---


def test_dynamic_attr_name() -> None:
    assert _el(parse('<div data-x="v">').find("div", attrs={"data-x": "v"})).tag == "div"


@pytest.mark.parametrize(
    "attrs",
    [
        pytest.param({"data-missing": True}, id="name-unseen-in-tree"),
        pytest.param({"": True}, id="empty-name"),
    ],
)
def test_attrs_dict_matches_nothing(attrs: dict[str, Filter]) -> None:
    assert parse("<div>").find_all("div", attrs=attrs) == []


# --- a list filter propagates an error from a member, as does a direct callable ---


@pytest.mark.parametrize(
    "id_filter",
    [
        pytest.param(_raise, id="direct-callable"),
        pytest.param([re.compile(r"z"), _raise], id="callable-in-list"),
    ],
)
def test_callable_error_propagates(id_filter: Filter) -> None:
    with pytest.raises(ZeroDivisionError):
        parse("<p>").find(id=id_filter)


# --- argument errors ---


@pytest.mark.parametrize(
    "call",
    [
        # axis must be an Axis member; a str is rejected at runtime
        pytest.param(lambda: parse(_DOC).find("p", axis="descendants"), id="bad-axis-type"),  # ty: ignore[invalid-argument-type]
        # limit must be an int or None; a str is rejected at runtime
        pytest.param(lambda: parse(_DOC).find_all("p", limit="lots"), id="bad-limit-type"),  # ty: ignore[invalid-argument-type]
        # attrs must be a Mapping; a list is rejected at runtime
        pytest.param(lambda: parse(_DOC).find("p", attrs=["id"]), id="attrs-not-a-mapping"),  # ty: ignore[invalid-argument-type]
        # a non-str attribute name is rejected at runtime
        pytest.param(lambda: parse(_DOC).find("p", attrs={1: "x"}), id="attr-name-not-a-str"),  # ty: ignore[invalid-argument-type]
        # an int is not a valid filter type
        pytest.param(lambda: parse("<p>").find(id=123), id="unknown-filter-type"),  # ty: ignore[invalid-argument-type]
    ],
)
def test_type_errors(call: Callable[[], object]) -> None:
    with pytest.raises(TypeError):
        call()
