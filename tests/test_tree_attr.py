"""Element.attr(): the raw attribute value as a single str, with a default for absence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from turbohtml import Element


def first(html: str, tag: str) -> Element:
    element = parse(html).select_one(tag)
    assert element is not None
    return element


@pytest.mark.parametrize(
    ("html", "tag", "name", "expected"),
    [
        pytest.param('<a href="/x">', "a", "href", "/x", id="plain-value"),
        pytest.param('<a HREF="/x">', "a", "href", "/x", id="name-lowercased"),
        pytest.param('<div class="a b c">', "div", "class", "a b c", id="class-stays-raw-string"),
        pytest.param('<a rel="next prefetch">', "a", "rel", "next prefetch", id="token-list-stays-raw"),
        pytest.param("<input disabled>", "input", "disabled", "", id="valueless-is-empty-string"),
        pytest.param('<a href="">', "a", "href", "", id="empty-value"),
    ],
)
def test_attr_returns_raw_value(html: str, tag: str, name: str, expected: str) -> None:
    assert first(html, tag).attr(name) == expected


def test_attr_absent_defaults_to_none() -> None:
    assert first("<a href='/x'>", "a").attr("title") is None


def test_attr_absent_returns_given_default() -> None:
    assert first("<a href='/x'>", "a").attr("title", "fallback") == "fallback"


def test_attr_default_is_keyword() -> None:
    assert first("<a href='/x'>", "a").attr("title", default="kw") == "kw"


def test_attr_present_ignores_default() -> None:
    assert first('<a href="/x">', "a").attr("href", "fallback") == "/x"


def test_attr_name_must_be_str() -> None:
    with pytest.raises(TypeError, match="attribute name must be a str"):
        first('<a href="/x">', "a").attr(123)  # type: ignore[arg-type]


def test_attr_requires_a_name() -> None:
    with pytest.raises(TypeError):
        first('<a href="/x">', "a").attr()  # type: ignore[call-arg]


def test_attr_getall_over_a_selection_is_a_comprehension() -> None:
    doc = parse('<a href="/x">home</a><a href="/y">about</a>')
    assert [anchor.attr("href") for anchor in doc.select("a")] == ["/x", "/y"]
