"""The compiled Matcher's soupsieve-shaped bound methods over the native engine."""

from __future__ import annotations

from typing import cast

import pytest

from turbohtml import Element, parse
from turbohtml.query import (  # the soupsieve names
    DEBUG,
    Matching,
    SelectorSyntaxError,
    closest,
    compile,  # ruff:ignore[builtin-import-shadowing]  # the soupsieve entry-point name
    css,
    escape_identifier,
    filter,  # ruff:ignore[builtin-import-shadowing]  # the soupsieve name
    iselect,
    match,
    select,
    select_one,
)

_DOC = "<div><a href=x>one</a><span><a href=y>two</a></span><a>bare</a></div>"


def _root() -> Element:
    root = parse(_DOC).root
    assert root is not None
    return root


def test_compile_returns_a_reusable_matcher() -> None:
    matcher = compile("a[href]")
    first, second = matcher.select(_root()), matcher.select(_root())
    assert [node.attr("href") for node in first] == [node.attr("href") for node in second] == ["x", "y"]


def test_css_is_a_compile_alias() -> None:
    assert [node.tag for node in css("a[href]").select(_root())] == ["a", "a"]


def test_select_returns_descendants_in_document_order() -> None:
    assert [node.attr("href") for node in compile("a[href]").select(_root())] == ["x", "y"]


def test_select_limit_caps_the_result() -> None:
    assert [node.attr("href") for node in compile("a[href]").select(_root(), limit=1)] == ["x"]


def test_select_zero_limit_returns_all() -> None:
    assert len(compile("a[href]").select(_root(), limit=0)) == 2


def test_select_one_returns_the_first_match() -> None:
    found = compile("a[href]").select_one(_root())
    assert found is not None
    assert found.attr("href") == "x"


def test_select_one_returns_none_when_absent() -> None:
    assert compile("table").select_one(_root()) is None


def test_iselect_yields_lazily() -> None:
    assert [node.attr("href") for node in compile("a[href]").iselect(_root())] == ["x", "y"]


def test_iselect_limit_caps_the_stream() -> None:
    assert [node.attr("href") for node in compile("a[href]").iselect(_root(), limit=1)] == ["x"]


def test_match_tests_a_single_element() -> None:
    anchor = compile("a[href]").select_one(_root())
    assert anchor is not None
    assert compile("a[href]").match(anchor) is True


def test_match_is_false_for_a_non_match() -> None:
    assert compile("a[href]").match(_root()) is False


def test_filter_keeps_matching_members_of_an_iterable() -> None:
    anchors = _root().select("a")
    assert [node.attr("href") for node in compile("[href]").filter(anchors)] == ["x", "y"]


def test_filter_accepts_a_generator() -> None:
    anchors = _root().select("a")
    assert [node.attr("href") for node in compile("[href]").filter(node for node in anchors)] == ["x", "y"]


def test_filter_preserves_order_and_duplicates_across_trees() -> None:
    first = parse("<a id=first class=hit></a><a id=miss></a>").select("a")
    second = parse("<a id=second class=hit></a>").select_one("a")
    assert second is not None
    assert [node.attr("id") for node in compile(".hit").filter([second, first[1], first[0], second])] == [
        "second",
        "first",
        "second",
    ]


@pytest.mark.parametrize(
    "candidates",
    [
        pytest.param([1], id="first"),
        pytest.param([_root(), 1], id="later"),
    ],
)
def test_filter_rejects_non_elements(candidates: list[object]) -> None:
    with pytest.raises(TypeError, match="filter candidates must be Element instances"):
        compile("*").filter(cast("list[Element]", candidates))


def test_filter_on_an_element_tests_its_direct_children() -> None:
    parent = parse("<div>text<a href=x>k</a><span><a href=deep>d</a></span><b>n</b></div>").select_one("div")
    assert parent is not None
    assert [node.tag for node in compile("a, span").filter(parent)] == ["a", "span"]


def test_closest_walks_up_to_the_nearest_match() -> None:
    anchor = compile("a[href=y]").select_one(_root())
    assert anchor is not None
    found = compile("div").closest(anchor)
    assert found is not None
    assert found.tag == "div"


def test_closest_returns_none_without_a_match() -> None:
    anchor = compile("a[href=x]").select_one(_root())
    assert anchor is not None
    assert compile("table").closest(anchor) is None


def test_compile_rejects_a_malformed_selector() -> None:
    with pytest.raises(SelectorSyntaxError):
        compile("a[")


def test_selector_syntax_error_is_a_value_error() -> None:
    assert issubclass(SelectorSyntaxError, ValueError)


def test_pattern_exposes_the_selector() -> None:
    assert compile("div a").pattern == "div a"


def test_namespaces_and_flags_default_to_soupsieves() -> None:
    matcher = compile("a")
    assert matcher.namespaces is None
    assert matcher.flags == 0


def test_options_are_carried_on_the_matcher() -> None:
    matcher = compile("a", Matching(namespaces={"svg": "http://www.w3.org/2000/svg"}, flags=1))
    assert matcher.namespaces == {"svg": "http://www.w3.org/2000/svg"}
    assert matcher.flags == 1


def test_default_is_soupsieves_html_mode() -> None:
    assert Matching() == Matching(namespaces=None, flags=0)


def test_config_is_frozen() -> None:
    with pytest.raises(AttributeError):
        Matching().flags = 1  # ty: ignore[invalid-assignment]  # asserting the frozen dataclass rejects it


def test_soupsieve_preset_maps_the_call_convention() -> None:
    namespaces = {"svg": "http://www.w3.org/2000/svg"}
    config = Matching.soupsieve(namespaces=namespaces, flags=DEBUG)
    assert config == Matching(namespaces=namespaces, flags=DEBUG)


def test_soupsieve_preset_defaults_match_the_plain_config() -> None:
    assert Matching.soupsieve() == Matching()


def test_debug_flag_value() -> None:
    assert DEBUG == 0x1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("", "", id="empty"),
        pytest.param("foo", "foo", id="plain"),
        pytest.param("ABC", "ABC", id="uppercase-kept"),
        pytest.param("_x", "_x", id="underscore-kept"),
        pytest.param("a-", "a-", id="trailing-dash-kept"),
        pytest.param("café", "café", id="non-ascii-kept"),
        pytest.param("foo bar", "foo\\ bar", id="space-backslashed"),
        pytest.param("a#b.c", "a\\#b\\.c", id="punctuation-backslashed"),
        pytest.param("-", "\\-", id="lone-dash"),
        pytest.param("--", "--", id="double-dash-kept"),
        pytest.param("-1", "-\\31 ", id="dash-then-digit"),
        pytest.param("12ab", "\\31 2ab", id="leading-digit"),
        pytest.param("0", "\\30 ", id="lone-digit"),
        pytest.param("a\tb", "a\\9 b", id="interior-control"),
        pytest.param("\x7f", "\\7f ", id="delete-char"),
        pytest.param("\x00abc", "�abc", id="null-to-replacement"),
        pytest.param("a1b", "a1b", id="digit-after-letter-stays"),
        pytest.param("1-", "\\31 -", id="leading-digit-then-dash"),
        pytest.param("-a1", "-a1", id="dash-letter-digit"),
    ],
)
def test_escape_matches_cssom(raw: str, expected: str) -> None:
    assert escape_identifier(raw) == expected


def test_non_str_identifier_raises_type_error() -> None:
    with pytest.raises(TypeError, match="must be str"):
        escape_identifier(cast("str", b"raw-bytes"))


_MODULE_DOC = "<div><a href=x>one</a><span><a href=y>two</a></span></div>"


def _module_root() -> Element:
    root = parse(_MODULE_DOC).root
    assert root is not None
    return root


def test_select_collects_matches() -> None:
    assert [node.attr("href") for node in select("a[href]", _module_root())] == ["x", "y"]


def test_select_honors_limit() -> None:
    assert [node.attr("href") for node in select("a[href]", _module_root(), limit=1)] == ["x"]


def test_select_one_returns_first() -> None:
    found = select_one("a[href]", _module_root())
    assert found is not None
    assert found.attr("href") == "x"


def test_iselect_iterates_matches() -> None:
    assert [node.attr("href") for node in iselect("a[href]", _module_root(), limit=2)] == ["x", "y"]


def test_match_tests_an_element() -> None:
    anchor = select_one("a[href]", _module_root())
    assert anchor is not None
    assert match("a[href]", anchor) is True


def test_filter_keeps_matching_members() -> None:
    anchors = _module_root().select("a")
    assert [node.attr("href") for node in filter("[href=y]", anchors)] == ["y"]


def test_closest_walks_up() -> None:
    anchor = select_one("a[href=y]", _module_root())
    assert anchor is not None
    found = closest("div", anchor)
    assert found is not None
    assert found.tag == "div"
