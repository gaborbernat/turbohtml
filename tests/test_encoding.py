"""parse(bytes): the WHATWG encoding sniffing order and decoding."""

from __future__ import annotations

import pytest

from turbohtml import parse


def test_str_input_has_no_encoding() -> None:
    assert parse("<p>hi</p>").encoding is None


def test_undeclared_bytes_default_to_windows_1252() -> None:
    # no BOM, argument, or <meta>: the WHATWG default applies
    assert parse(b"<p>hi</p>").encoding == "windows-1252"


def test_meta_charset_is_decoded() -> None:
    doc = parse('<meta charset="utf-8"><p>café</p>'.encode())
    assert doc.encoding == "UTF-8"
    element = doc.find("p")
    assert element is not None
    assert element.text == "café"


@pytest.mark.parametrize(
    ("data", "encoding"),
    [
        pytest.param(b"\xef\xbb\xbf<p>x", "UTF-8", id="utf-8"),
        pytest.param(b"\xff\xfe<\x00p\x00>\x00", "UTF-16LE", id="utf-16le"),
        pytest.param(b"\xfe\xff\x00<\x00p\x00>", "UTF-16BE", id="utf-16be"),
    ],
)
def test_bom_is_detected_and_stripped(data: bytes, encoding: str) -> None:
    doc = parse(data)
    assert doc.encoding == encoding
    element = doc.find("p")
    assert element is not None  # the byte-order mark did not leak into the tree


def test_encoding_argument_is_used() -> None:
    assert parse(b"<p>x", encoding="iso-8859-2").encoding == "iso-8859-2"


def test_bom_overrides_the_encoding_argument() -> None:
    assert parse(b"\xef\xbb\xbf<p>x", encoding="iso-8859-2").encoding == "UTF-8"


def test_meta_overrides_the_argument_only_when_no_argument() -> None:
    # the argument outranks a <meta>; a <meta> is used only without an argument
    assert parse(b'<meta charset="utf-8"><p>x', encoding="iso-8859-2").encoding == "iso-8859-2"


@pytest.mark.parametrize("wrap", [bytes, bytearray, memoryview], ids=["bytes", "bytearray", "memoryview"])
def test_bytes_like_inputs(wrap: type) -> None:
    assert parse(wrap(b'<meta charset="iso-8859-2"><p>x')).encoding == "iso-8859-2"


def test_invalid_bytes_become_replacement_characters() -> None:
    # 0xFF is not valid UTF-8; decoding replaces it instead of raising
    doc = parse(b'<meta charset="utf-8"><p>\xff</p>')
    element = doc.find("p")
    assert element is not None
    assert element.text == "�"


def test_unknown_argument_label_falls_through_to_default() -> None:
    assert parse(b"<p>x", encoding="not-a-real-encoding").encoding == "windows-1252"


def test_argument_label_is_whitespace_and_case_insensitive() -> None:
    assert parse(b"<p>x", encoding="  ISO-8859-2  ").encoding == "iso-8859-2"


@pytest.mark.parametrize("label", ["", "   ", "x" * 80], ids=["empty", "whitespace", "overlong"])
def test_unusable_argument_label_falls_through(label: str) -> None:
    assert parse(b"<p>x", encoding=label).encoding == "windows-1252"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        # byte-order-mark near misses fall through to the default
        pytest.param(b"a", "windows-1252", id="one-byte"),
        pytest.param(b"ab", "windows-1252", id="two-byte-no-bom"),
        pytest.param(b"\xefab", "windows-1252", id="ef-not-bb"),
        pytest.param(b"\xef\xbba", "windows-1252", id="ef-bb-not-bf"),
        pytest.param(b"\xfea", "windows-1252", id="fe-not-ff"),
        pytest.param(b"\xffa", "windows-1252", id="ff-not-fe"),
        # not actually a meta element
        pytest.param(b"<meto charset=utf-8>", "windows-1252", id="not-meta-name"),
        pytest.param(b"<metax>", "windows-1252", id="meta-no-space"),
        # attribute parsing edges
        pytest.param(b"<meta charset", "windows-1252", id="name-at-eof"),
        pytest.param(b"<meta charset=>", "windows-1252", id="empty-value"),
        pytest.param(b'<meta foo charset="utf-8">', "UTF-8", id="bare-attribute"),
        pytest.param(b"<meta " + b"a" * 40 + b'=x charset="utf-8">', "UTF-8", id="long-name"),
        pytest.param(b'<meta charset="' + b"z" * 200 + b'">', "windows-1252", id="long-quoted-value"),
        pytest.param(b"<meta charset=" + b"z" * 200 + b">", "windows-1252", id="long-unquoted-value"),
        # http-equiv / content
        pytest.param(b'<meta http-equiv="content-type" content="charset">', "windows-1252", id="content-no-eq"),
        pytest.param(
            b'<meta http-equiv="content-type" content="text/html; charset=utf-8; x">', "UTF-8", id="content-semicolon"
        ),
        pytest.param(
            b'<meta http-equiv="content-type" content="text/html; charset=\'utf-8\'">', "UTF-8", id="content-quoted"
        ),
        pytest.param(b'<meta http-equiv="refresh" content="0; charset=utf-8">', "windows-1252", id="not-pragma"),
        # tag skipping
        pytest.param(b'</p><meta charset="utf-8">', "UTF-8", id="end-tag-then-meta"),
        pytest.param(b'<?xml?><meta charset="utf-8">', "UTF-8", id="pi-then-meta"),
        pytest.param(b"<!-- unterminated", "windows-1252", id="unterminated-comment"),
        # a quoted attribute hides a later meta until its closing quote
        pytest.param(b'<p title="x><meta charset=utf-8"><p>', "windows-1252", id="meta-inside-quote"),
        # attribute-name and value lexing corners
        pytest.param(b'<meta =x charset="utf-8">', "UTF-8", id="equals-first"),
        pytest.param(b"<meta charset =utf-8>", "UTF-8", id="space-before-equals"),
        pytest.param(b"<meta charset ", "windows-1252", id="name-then-space-eof"),
        pytest.param(b'<meta CHARSET="utf-8">', "UTF-8", id="uppercase-name"),
        pytest.param(b"<meta charset=UTF-8>", "UTF-8", id="uppercase-value"),
        # content-attribute quote and truncation corners
        pytest.param(
            b'<meta http-equiv="content-type" content=\'text/html; charset="utf-8"\'>', "UTF-8", id="content-dquote"
        ),
        pytest.param(
            b'<meta http-equiv="content-type" content="charset=\'' + b"z" * 70 + b"'\">",
            "windows-1252",
            id="content-quoted-long",
        ),
        pytest.param(
            b'<meta http-equiv="content-type" content="charset=' + b"z" * 70 + b'">',
            "windows-1252",
            id="content-unquoted-long",
        ),
        pytest.param(b'<meta http-equiv="content-type" content="charset=">', "windows-1252", id="content-empty"),
        # an earlier charset wins, so the content attribute is not consulted
        pytest.param(
            b'<meta charset=utf-8 content="text/html; charset=iso-8859-2">', "UTF-8", id="charset-before-content"
        ),
        # meta-name near misses are skipped as ordinary tags
        pytest.param(b'<mq><meta charset="utf-8">', "UTF-8", id="m-not-me"),
        pytest.param(b'<meq><meta charset="utf-8">', "UTF-8", id="me-not-met"),
        # tag-skip combinator corners
        pytest.param(b'</1><meta charset="utf-8">', "UTF-8", id="end-tag-non-alpha"),
        pytest.param(b"</", "windows-1252", id="bare-end-tag"),
        pytest.param(b'< <meta charset="utf-8">', "UTF-8", id="lone-angle"),
    ],
)
def test_sniffing_edge_cases(data: bytes, expected: str) -> None:
    assert parse(data).encoding == expected


def test_parse_requires_an_argument() -> None:
    with pytest.raises(TypeError):
        parse()  # ty: ignore[missing-argument]  # the missing markup is rejected at runtime
