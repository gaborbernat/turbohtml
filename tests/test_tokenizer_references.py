"""Tokenizer surface for unresolved character references and verbatim source.

``resolve_references=False`` splits each character reference in text into its own
``CHARACTER_REFERENCE`` token; ``capture_source=True`` records the verbatim
source slice of every markup token as ``Token.source``. Both are off-equivalent
by default, so the existing token stream is unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import Token, Tokenizer, TokenType, tokenize

if TYPE_CHECKING:
    from collections.abc import Iterable


def _shape(token: Token) -> tuple[object, ...]:
    return (token.type, token.tag, token.data, token.source, token.attrs, token.self_closing)


def _stream_char_by_char(document: str, *, resolve_references: bool, capture_source: bool) -> list[Token]:
    tokenizer = Tokenizer(resolve_references=resolve_references, capture_source=capture_source)
    streamed = [token for char in document for token in tokenizer.feed(char)]
    streamed += list(tokenizer.close())
    return streamed


def _refs(tokens: Iterable[Token]) -> list[tuple[str | None, str | None]]:
    return [(token.data, token.source) for token in tokens if token.type is TokenType.CHARACTER_REFERENCE]


def test_default_resolves_references_into_text() -> None:
    head, tag = list(tokenize("a&amp;b<p>"))
    assert _shape(head) == (TokenType.TEXT, None, "a&b", None, None, False)
    assert tag.type is TokenType.START_TAG


def test_default_source_is_none() -> None:
    assert all(token.source is None for token in tokenize('<a href="x">hi</a>&amp;'))


@pytest.mark.parametrize(
    ("document", "data", "source"),
    [
        pytest.param("&amp;", "&", "&amp;", id="named"),
        pytest.param("&#x41;", "A", "&#x41;", id="numeric-hex"),
        pytest.param("&#65;", "A", "&#65;", id="numeric-dec"),
        pytest.param("&cent;", "¢", "&cent;", id="named-two-byte"),
        pytest.param("&notin;", "∉", "&notin;", id="named-astral-name"),
        pytest.param("&amp", "&", "&amp", id="named-no-semicolon"),
        pytest.param("&gt;", ">", "&gt;", id="named-gt"),
    ],
)
def test_reference_becomes_its_own_token(document: str, data: str, source: str) -> None:
    (reference,) = list(tokenize(document, resolve_references=False))
    assert reference.type is TokenType.CHARACTER_REFERENCE
    assert reference.data == data
    assert reference.source == source
    assert reference.tag is None
    assert reference.attrs is None
    assert reference.self_closing is False


def test_reference_splits_surrounding_text() -> None:
    tokens = list(tokenize("a&amp;b", resolve_references=False))
    assert [(token.type, token.data) for token in tokens] == [
        (TokenType.TEXT, "a"),
        (TokenType.CHARACTER_REFERENCE, "&"),
        (TokenType.TEXT, "b"),
    ]


@pytest.mark.parametrize(
    ("document", "text"),
    [
        pytest.param("a & b", "a & b", id="bare-ampersand-space"),
        pytest.param("&xyz", "&xyz", id="unknown-name-no-semicolon"),
        pytest.param("&#", "&#", id="numeric-no-digits"),
        pytest.param("&#x", "&#x", id="hex-no-digits"),
        pytest.param("x&", "x&", id="trailing-ampersand-at-eof"),
    ],
)
def test_non_reference_ampersand_stays_text(document: str, text: str) -> None:
    tokens = list(tokenize(document, resolve_references=False))
    assert all(token.type is TokenType.TEXT for token in tokens)
    assert "".join(token.data or "" for token in tokens) == text


def test_consecutive_references() -> None:
    assert _refs(tokenize("&amp;&lt;&gt;", resolve_references=False)) == [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;")]


def test_named_vs_numeric_is_readable_from_source() -> None:
    named, numeric = (token.source for token in tokenize("&amp;&#65;", resolve_references=False))
    assert named is not None
    assert numeric is not None
    # the verbatim source distinguishes the two: a numeric reference's second character is '#'
    assert (named[1], numeric[1]) == ("a", "#")


def test_references_split_in_rcdata() -> None:
    tokens = list(tokenize("<title>x&amp;y</title>", resolve_references=False))
    assert _refs(tokens) == [("&", "&amp;")]
    assert [token.data for token in tokens if token.type is TokenType.TEXT] == ["x", "y"]


def test_non_reference_ampersand_stays_text_in_rcdata() -> None:
    tokens = list(tokenize("<title>a & b</title>", resolve_references=False))
    assert [token.data for token in tokens if token.type is TokenType.TEXT] == ["a & b"]
    assert not any(token.type is TokenType.CHARACTER_REFERENCE for token in tokens)


def test_attribute_references_always_resolved() -> None:
    # convert_charrefs-style splitting applies to text only; the attribute list stays decoded
    (tag,) = list(tokenize('<a href="a&amp;b">', resolve_references=False))
    assert tag.type is TokenType.START_TAG
    assert tag.attrs == [("href", "a&b")]


def test_reference_repr() -> None:
    (reference,) = list(tokenize("&amp;", resolve_references=False))
    assert repr(reference) == "Token(CHARACTER_REFERENCE, data='&')"


@pytest.mark.parametrize(
    ("document", "tag", "source"),
    [
        pytest.param('<a href="x">', "a", '<a href="x">', id="start-tag"),
        pytest.param("</a>", "a", "</a>", id="end-tag"),
        pytest.param("<br/>", "br", "<br/>", id="self-closing"),
        pytest.param("<!--c-->", None, "<!--c-->", id="comment"),
        pytest.param("<!DOCTYPE html>", None, "<!DOCTYPE html>", id="doctype"),
    ],
)
def test_capture_source_records_verbatim_markup(document: str, tag: str | None, source: str) -> None:
    (token,) = list(tokenize(document, capture_source=True))
    assert token.tag == tag
    assert token.source == source


def test_capture_source_leaves_text_without_source() -> None:
    start, text, end = list(tokenize("<p>hi</p>", capture_source=True))
    assert start.source == "<p>"
    assert text.type is TokenType.TEXT
    assert text.source is None
    assert end.source == "</p>"


def test_capture_source_preserves_original_casing_and_whitespace() -> None:
    # the resolved tag name is lowercased, but the verbatim source keeps the original spelling
    (tag,) = list(tokenize("<DIV  Class = 'x' >", capture_source=True))
    assert tag.tag == "div"
    assert tag.source == "<DIV  Class = 'x' >"


def test_capture_source_and_split_references_combine() -> None:
    tokens = list(tokenize("<p>a&amp;b</p>", resolve_references=False, capture_source=True))
    assert [(token.type, token.source) for token in tokens] == [
        (TokenType.START_TAG, "<p>"),
        (TokenType.TEXT, None),
        (TokenType.CHARACTER_REFERENCE, "&amp;"),
        (TokenType.TEXT, None),
        (TokenType.END_TAG, "</p>"),
    ]


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("a&amp;b&#x41;c&#65;d&cent;&notin;&unknown;e", id="mixed-references"),
        pytest.param("x & y &amp z &# w", id="literal-ampersands"),
        pytest.param("<title>r&amp;c</title>&gt;", id="rcdata-and-data"),
        pytest.param("<title>a & b &x</title>", id="rcdata-literal-ampersand"),
        pytest.param("&amp;&lt;&gt;", id="adjacent"),
    ],
)
def test_split_streaming_matches_whole(document: str, width_prefix: str) -> None:
    text = width_prefix + document
    streamed = _stream_char_by_char(text, resolve_references=False, capture_source=False)
    whole = list(tokenize(text, resolve_references=False))
    assert [_shape(token) for token in streamed] == [_shape(token) for token in whole]
    assert [(token.line, token.col) for token in streamed] == [(token.line, token.col) for token in whole]


@pytest.mark.parametrize(
    "document",
    [
        pytest.param('<a href="x" id=y>hi</a><!--c--><br/>', id="tags-and-comment"),
        pytest.param("<DIV Class='X'>t</DIV>", id="casing"),
        pytest.param("<!DOCTYPE html><p>x", id="doctype"),
        pytest.param("<a\n href='x'\n>y", id="multiline-tag"),
    ],
)
def test_capture_source_streaming_matches_whole(document: str, width_prefix: str) -> None:
    text = width_prefix + document
    streamed = _stream_char_by_char(text, resolve_references=True, capture_source=True)
    whole = list(tokenize(text, capture_source=True))
    assert [_shape(token) for token in streamed] == [_shape(token) for token in whole]


def test_capture_source_spans_a_feed_boundary() -> None:
    # the opening '<' is in an earlier chunk than the closing '>', so input compaction
    # between feeds must keep the tag's source prefix alive (issue #213); here a pending
    # text run ("a") already pins the prefix
    tokenizer = Tokenizer(capture_source=True)
    tokens = list(tokenizer.feed("a<a "))
    tokens += list(tokenizer.feed('href="x">b'))
    tokens += list(tokenizer.close())
    start = next(token for token in tokens if token.type is TokenType.START_TAG)
    assert start.source == '<a href="x">'


def test_capture_source_spans_feed_boundary_without_leading_text() -> None:
    # a tag opens a chunk with nothing buffered before it, so only the marked '<' itself
    # keeps the prefix alive across the next feed's compaction
    tokenizer = Tokenizer(capture_source=True)
    list(tokenizer.feed("<a>"))  # emits and drains, leaving no pending text
    list(tokenizer.feed("<b "))  # opens a tag with nothing buffered ahead of it
    tokens = [*tokenizer.feed('x="y">'), *tokenizer.close()]
    start = next(token for token in tokens if token.tag == "b")
    assert start.source == '<b x="y">'


def test_tokenize_rejects_unknown_keyword() -> None:
    with pytest.raises(TypeError):
        tokenize("x", flavor=1)  # ty: ignore[unknown-argument]  # unexpected keyword on purpose


def test_capture_source_survives_many_streamed_tags() -> None:
    # drive enough feeds that the input buffer compacts repeatedly while sources resolve
    tokenizer = Tokenizer(capture_source=True)
    sources: list[str | None] = []
    for index in range(50):
        sources.extend(
            token.source for token in tokenizer.feed(f"<p id={index}>x</p>") if token.type is TokenType.START_TAG
        )
    sources += [token.source for token in tokenizer.close() if token.type is TokenType.START_TAG]
    assert sources == [f"<p id={index}>" for index in range(50)]


def test_split_reference_survives_a_queued_feed() -> None:
    # a reference token left queued behind a flushed text run must keep a valid source
    # across the next feed's compaction
    tokenizer = Tokenizer(resolve_references=False)
    stream = tokenizer.feed("x&amp;")
    first = next(stream)
    tokenizer.feed("y")
    tokens = [first, *tokenizer, *tokenizer.close()]
    assert _refs(tokens) == [("&", "&amp;")]
    assert [token.data for token in tokens if token.type is TokenType.TEXT] == ["x", "y"]
