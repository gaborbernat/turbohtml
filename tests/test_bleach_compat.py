from __future__ import annotations

import pytest

from turbohtml.bleach_compat import ALLOWED_ATTRIBUTES, ALLOWED_PROTOCOLS, ALLOWED_TAGS, clean


def test_clean_defaults_match_bleach() -> None:
    assert clean("<a href='http://x'>ok</a> <script>bad()</script>") == (
        '<a href="http://x">ok</a> &lt;script&gt;bad()&lt;/script&gt;'
    )


def test_clean_drops_javascript_url() -> None:
    assert clean("<a href='javascript:alert(1)'>x</a>") == "<a>x</a>"


def test_clean_custom_tags() -> None:
    assert clean("<b>keep</b><i>drop</i>", tags=["b"]) == "<b>keep</b>&lt;i&gt;drop&lt;/i&gt;"


def test_clean_attributes_as_list() -> None:
    assert clean('<b class="c" id="i">x</b>', tags=["b"], attributes=["class"]) == '<b class="c">x</b>'


def test_clean_attributes_as_dict() -> None:
    out = clean('<a href="http://x" title="t" rel="r">y</a>', tags=["a"], attributes={"a": ["href", "title"]})
    assert out == '<a href="http://x" title="t">y</a>'


def test_clean_attributes_as_callable() -> None:
    keep_data = clean(
        '<b data-x="1" id="i">y</b>', tags=["b"], attributes=lambda _tag, name, _value: name.startswith("data-")
    )
    assert keep_data == '<b data-x="1">y</b>'


def test_clean_attributes_as_per_tag_callable() -> None:
    out = clean(
        '<a href="http://x" data-z="1">y</a><b data-z="1">z</b>',
        tags=["a", "b"],
        attributes={"a": lambda _tag, name, _value: name == "href", "b": ["data-z"]},
    )
    assert out == '<a href="http://x">y</a><b data-z="1">z</b>'


def test_clean_attributes_as_wildcard_callable() -> None:
    # a "*" callable applies to every tag; it must drop the disallowed attribute, not fail open
    out = clean(
        '<a href="/foo" title="t">x</a>', tags=["a"], attributes={"*": lambda _tag, name, _val: name == "title"}
    )
    assert out == '<a title="t">x</a>'


def test_clean_protocols() -> None:
    assert clean('<a href="ftp://x">y</a>', tags=["a"], attributes={"a": ["href"]}, protocols=["ftp"]) == (
        '<a href="ftp://x">y</a>'
    )


def test_clean_strip_true_unwraps() -> None:
    assert clean("<div><b>x</b></div>", strip=True) == "<b>x</b>"


def test_clean_strip_false_escapes() -> None:
    assert clean("<div><b>x</b></div>", strip=False) == "&lt;div&gt;<b>x</b>&lt;/div&gt;"


def test_clean_strip_comments_default() -> None:
    assert clean("a<!-- c -->b") == "ab"


def test_clean_keep_comments() -> None:
    assert clean("a<!-- c -->b", strip_comments=False) == "a<!-- c -->b"


def test_clean_css_sanitizer_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="css_sanitizer"):
        clean("<p>x</p>", css_sanitizer=object())


def test_exported_constants() -> None:
    assert "a" in ALLOWED_TAGS
    assert ALLOWED_ATTRIBUTES["a"] == frozenset({"href", "title"})
    assert frozenset({"http", "https", "mailto"}) == ALLOWED_PROTOCOLS
