"""Node.re() / Node.re_first(): regex over a node's text or one of its attributes."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from turbohtml import Element


def first(html: str, tag: str) -> Element:
    element = parse(html).select_one(tag)
    assert element is not None
    return element


def test_re_no_group_returns_whole_matches() -> None:
    paragraph = first("<p>cat hat bat</p>", "p")
    assert paragraph.re(r"\w+at") == ["cat", "hat", "bat"]


def test_re_one_group_returns_that_group() -> None:
    paragraph = first("<p>id: 42, id: 7</p>", "p")
    assert paragraph.re(r"id: (\d+)") == ["42", "7"]


def test_re_two_groups_falls_back_to_whole_match() -> None:
    paragraph = first("<p>a=1 b=2</p>", "p")
    assert paragraph.re(r"(\w)=(\d)") == ["a=1", "b=2"]


def test_re_no_match_is_empty_list() -> None:
    assert first("<p>nothing</p>", "p").re(r"\d+") == []


def test_re_accepts_a_compiled_pattern() -> None:
    paragraph = first("<p>CAT cat</p>", "p")
    assert paragraph.re(re.compile(r"cat", re.IGNORECASE)) == ["CAT", "cat"]


def test_re_over_descendant_text() -> None:
    div = first("<div><b>foo</b> <i>bar</i></div>", "div")
    assert div.re(r"\w+") == ["foo", "bar"]


def test_re_over_attribute_value() -> None:
    anchor = first('<a href="/item/42/detail">x</a>', "a")
    assert anchor.re(r"/item/(\d+)", attr="href") == ["42"]


def test_re_over_absent_attribute_is_empty() -> None:
    assert first('<a href="/x">x</a>', "a").re(r"\d+", attr="title") == []


def test_re_attr_none_runs_over_text() -> None:
    paragraph = first("<p>year 2026</p>", "p")
    assert paragraph.re(r"\d+", attr=None) == ["2026"]


def test_re_over_valueless_attribute_is_empty() -> None:
    assert first("<input disabled>", "input").re(r".+", attr="disabled") == []


def test_re_bad_pattern_type() -> None:
    with pytest.raises(TypeError, match=r"pattern must be a str or a compiled re\.Pattern"):
        first("<p>x</p>", "p").re(123)  # ty: ignore[invalid-argument-type]


def test_re_invalid_regex_propagates() -> None:
    with pytest.raises(re.error):
        first("<p>x</p>", "p").re(r"(")


def test_re_attr_name_must_be_str() -> None:
    with pytest.raises(TypeError, match="attribute name must be a str"):
        first("<p>x</p>", "p").re(r"\d+", attr=123)  # ty: ignore[invalid-argument-type]


def test_re_first_returns_first_whole_match() -> None:
    assert first("<p>cat hat</p>", "p").re_first(r"\w+at") == "cat"


def test_re_first_returns_first_group() -> None:
    assert first("<p>id: 42, id: 7</p>", "p").re_first(r"id: (\d+)") == "42"


def test_re_first_two_groups_falls_back_to_whole_match() -> None:
    assert first("<p>a=1 b=2</p>", "p").re_first(r"(\w)=(\d)") == "a=1"


def test_re_first_no_match_defaults_to_none() -> None:
    assert first("<p>nothing</p>", "p").re_first(r"\d+") is None


def test_re_first_no_match_returns_given_default() -> None:
    assert first("<p>nothing</p>", "p").re_first(r"\d+", "missing") == "missing"


def test_re_first_default_is_keyword() -> None:
    assert first("<p>nothing</p>", "p").re_first(r"\d+", default="kw") == "kw"


def test_re_first_over_attribute_value() -> None:
    anchor = first('<a href="/item/42">x</a>', "a")
    assert anchor.re_first(r"/item/(\d+)", attr="href") == "42"


def test_re_first_over_absent_attribute_uses_default() -> None:
    assert first('<a href="/x">x</a>', "a").re_first(r"\d+", "none", attr="title") == "none"


def test_re_first_over_valueless_attribute_uses_default() -> None:
    assert first("<input disabled>", "input").re_first(r".+", "none", attr="disabled") == "none"


def test_re_first_bad_pattern_type() -> None:
    with pytest.raises(TypeError, match=r"pattern must be a str or a compiled re\.Pattern"):
        first("<p>x</p>", "p").re_first(123)  # ty: ignore[invalid-argument-type]


def test_re_first_attr_name_must_be_str() -> None:
    with pytest.raises(TypeError, match="attribute name must be a str"):
        first("<p>x</p>", "p").re_first(r"\d+", attr=123)  # ty: ignore[invalid-argument-type]


def test_re_requires_a_pattern() -> None:
    with pytest.raises(TypeError):
        first("<p>x</p>", "p").re()  # ty: ignore[missing-argument]


def test_re_first_requires_a_pattern() -> None:
    with pytest.raises(TypeError):
        first("<p>x</p>", "p").re_first()  # ty: ignore[missing-argument]
