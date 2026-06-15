"""Element.attrs: token-list attributes split to list[str], plus order and valueless rules."""

from __future__ import annotations

import pytest

from turbohtml import parse


@pytest.mark.parametrize(
    ("html", "tag", "attr", "expected"),
    [
        pytest.param('<div class="a b">', "div", "class", ["a", "b"], id="class"),
        pytest.param('<link sizes="16x16 32x32">', "link", "sizes", ["16x16", "32x32"], id="sizes"),
        pytest.param('<a rel="next prefetch">', "a", "rel", ["next", "prefetch"], id="rel"),
        pytest.param('<a rev="made up">', "a", "rev", ["made", "up"], id="rev"),
        pytest.param("<table><tr><td headers='h1 h2'>", "td", "headers", ["h1", "h2"], id="headers"),
        pytest.param(
            '<iframe sandbox="allow-forms allow-popups">',
            "iframe",
            "sandbox",
            ["allow-forms", "allow-popups"],
            id="sandbox",
        ),
        pytest.param('<object archive="a.jar b.jar">', "object", "archive", ["a.jar", "b.jar"], id="archive"),
        pytest.param('<div dropzone="copy link">', "div", "dropzone", ["copy", "link"], id="dropzone"),
        pytest.param('<button accesskey="s">', "button", "accesskey", ["s"], id="accesskey"),
        pytest.param(
            '<form accept-charset="utf-8 latin-1">',
            "form",
            "accept-charset",
            ["utf-8", "latin-1"],
            id="accept-charset",
        ),
    ],
)
def test_token_list_attributes_split(html: str, tag: str, attr: str, expected: list[str]) -> None:
    element = parse(html).find(tag)
    assert element is not None
    assert element.attrs[attr] == expected


@pytest.mark.parametrize(
    ("html", "tag", "attr"),
    [
        pytest.param('<div dir="ltr">', "div", "dir", id="len3"),
        pytest.param('<div title="t">', "div", "title", id="len5"),
        pytest.param('<div content="c">', "div", "content", id="len7"),
        pytest.param('<div tabindex="0">', "div", "tabindex", id="len8"),
        pytest.param('<div translate="no">', "div", "translate", id="len9"),
        pytest.param('<div data-foobar123="x">', "div", "data-foobar123", id="len14"),
        pytest.param('<div id="main">', "div", "id", id="default-length"),
    ],
)
def test_non_token_attributes_stay_string(html: str, tag: str, attr: str) -> None:
    element = parse(html).find(tag)
    assert element is not None
    assert isinstance(element.attrs[attr], str)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("a b", ["a", "b"], id="single-space"),
        pytest.param("  a   b  ", ["a", "b"], id="surrounding-and-internal"),
        pytest.param("solo", ["solo"], id="single-token"),
        pytest.param("   ", [], id="all-whitespace"),
        pytest.param("a\tb\nc\x0cd", ["a", "b", "c", "d"], id="every-ascii-whitespace"),
    ],
)
def test_class_whitespace_splitting(value: str, expected: list[str]) -> None:
    element = parse(f'<div class="{value}">').find("div")
    assert element is not None
    assert element.attrs["class"] == expected


@pytest.mark.parametrize(
    ("html", "tag", "attr"),
    [
        pytest.param("<div class>", "div", "class", id="valueless-token-list-name"),
        pytest.param('<div class="">', "div", "class", id="empty-value-token-list-name"),
        pytest.param("<input checked>", "input", "checked", id="valueless-plain-name"),
    ],
)
def test_valueless_attribute_is_none(html: str, tag: str, attr: str) -> None:
    element = parse(html).find(tag)
    assert element is not None
    assert element.attrs[attr] is None


def test_find_matches_token_attribute_by_whole_string() -> None:
    # find() compares the raw attribute value, so a token-list name is matched whole, not split.
    assert parse('<a rel="next">').find("a", rel="next") is not None
    assert parse('<a rel="next">').find("a", rel="nope") is None


def test_attribute_order_is_source_order() -> None:
    element = parse('<div id="a" class="x" data-z="1">').find("div")
    assert element is not None
    assert list(element.attrs) == ["id", "class", "data-z"]


def test_attrs_supports_mapping_protocol() -> None:
    element = parse('<div class="x y">').find("div")
    assert element is not None
    attrs = element.attrs
    assert attrs.get("class") == ["x", "y"]
    assert attrs.get("missing") is None
    assert "class" in attrs
    assert "missing" not in attrs
