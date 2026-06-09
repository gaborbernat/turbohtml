from __future__ import annotations

import pytest

import turbohtml


def test_escape_basic() -> None:
    assert turbohtml.escape("'<script>\"&foo;\"</script>'") == (
        "&#x27;&lt;script&gt;&quot;&amp;foo;&quot;&lt;/script&gt;&#x27;"
    )


def test_escape_quote_false() -> None:
    assert turbohtml.escape("'<script>\"&foo;\"</script>'", quote=False) == (
        "'&lt;script&gt;\"&amp;foo;\"&lt;/script&gt;'"
    )
    assert turbohtml.escape("\"'", quote=False) == "\"'"


def test_escape_quote_default_true() -> None:
    assert turbohtml.escape("\"'") == "&quot;&#x27;"


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param("a", id="single-char"),
        pytest.param("plain text", id="words"),
        pytest.param("x" * 100, id="long-ascii"),
        pytest.param("caf\xe9 r\xe9sum\xe9", id="latin1"),
        pytest.param("☃ snowman", id="ucs2"),
        pytest.param("\U0001f600 emoji", id="astral"),
    ],
)
def test_escape_no_specials_returns_equal(text: str) -> None:
    assert turbohtml.escape(text) == text


@pytest.mark.parametrize("pad", range(20))
@pytest.mark.parametrize(
    ("char", "rep"),
    [
        pytest.param("&", "&amp;", id="amp"),
        pytest.param("<", "&lt;", id="lt"),
        pytest.param(">", "&gt;", id="gt"),
        pytest.param('"', "&quot;", id="quot"),
        pytest.param("'", "&#x27;", id="apos"),
    ],
)
def test_escape_special_at_every_offset(pad: int, char: str, rep: str) -> None:
    head, tail = "a" * pad, "b" * pad
    assert turbohtml.escape(f"{head}{char}{tail}") == f"{head}{rep}{tail}"


def test_escape_adjacent_specials() -> None:
    assert turbohtml.escape("&<>\"'" * 5) == "&amp;&lt;&gt;&quot;&#x27;" * 5


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("☃ <b> & </b>", "☃ &lt;b&gt; &amp; &lt;/b&gt;", id="ucs2-with-specials"),
        pytest.param("\U0001f600<&>\"'", "\U0001f600&lt;&amp;&gt;&quot;&#x27;", id="astral-with-specials"),
        pytest.param("\xe9\xff & \xe9", "\xe9\xff &amp; \xe9", id="latin1-high-bytes"),
    ],
)
def test_escape_multiple_kinds(text: str, expected: str) -> None:
    assert turbohtml.escape(text) == expected


def test_escape_str_subclass_returns_true_str() -> None:
    class StrSubclass(str):  # noqa: FURB189  # subclassing str is the behavior under test
        __slots__ = ()

    result = turbohtml.escape(StrSubclass("a & b"))
    assert result == "a &amp; b"
    assert type(result) is str
    clean = turbohtml.escape(StrSubclass("clean"))
    assert clean == "clean"
    assert type(clean) is str


def test_escape_rejects_non_str() -> None:
    with pytest.raises(TypeError):
        turbohtml.escape(123)  # ty: ignore[invalid-argument-type]  # non-str on purpose to exercise the TypeError path
