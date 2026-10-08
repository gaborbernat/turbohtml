from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from fuzz.atheris_header import BYTEWISE, Header
from fuzz.atheris_parser_targets import (
    document_observation,
    fragment_observation,
    incremental_observation,
    parser_targets,
    token_observation,
)

from turbohtml import SourceLocation, SourceSpan

if TYPE_CHECKING:
    from fuzz.atheris_registry import Target


_UNPLACED: Final = ((None, None, None),) * 3


def test_atheris_parser_document_output() -> None:
    assert document_observation("<p>水😀</p>".encode()) == "<html><head></head><body><p>水😀</p></body></html>"


@pytest.mark.parametrize(
    ("header", "positions"),
    [
        pytest.param(BYTEWISE, (*_UNPLACED, (1, 0, None)), id="bytes-one-unit"),
        pytest.param(Header(1, 0, 2), (*_UNPLACED, (1, 0, None)), id="text-two-units"),
        pytest.param(Header(2, 0, 3), (*_UNPLACED, (None, None, None)), id="no-positions"),
        pytest.param(
            Header(4, 0, 5),
            (*_UNPLACED, (1, 0, SourceLocation(SourceSpan(1, 0, 0, 1, 3, 3), SourceSpan(1, 5, 5, 1, 9, 9), {}))),
            id="source-locations",
        ),
    ],
)
def test_atheris_parser_incremental_output(header: Header, positions: tuple[object, ...]) -> None:
    assert incremental_observation("<p>水😀</p>".encode(), header) == (
        "<html><head></head><body><p>水😀</p></body></html>",
        positions,
    )


def test_atheris_parser_fragment_output() -> None:
    assert fragment_observation(b"<p>x&amp;y</p>") == "<div><p>x&amp;y</p></div>"


def test_atheris_parser_token_fields() -> None:
    assert token_observation(b'<p id="a">x</p>') == (
        ("START_TAG", "p", None, (("id", "a"),), False, 1, 0),
        ("TEXT", None, "x", None, False, 1, 10),
        ("END_TAG", "p", None, (), False, 1, 11),
    )


@pytest.mark.parametrize(
    ("data", "opts", "expected"),
    [
        pytest.param(
            b"x&amp;",
            1,
            (
                ("TEXT", None, "x", None, False, 1, 0),
                ("CHARACTER_REFERENCE", None, "&", None, False, 1, 1),
            ),
            id="references-apart",
        ),
        pytest.param(b'<p id="a">', 4, (("START_TAG", "p", None, (), False, 1, 0),), id="no-attributes"),
    ],
)
def test_atheris_parser_token_options(data: bytes, opts: int, expected: tuple[object, ...]) -> None:
    assert token_observation(data, Header(opts, 0, 2)) == expected


@pytest.mark.parametrize(
    "oracle",
    [
        pytest.param("html", id="html-fixpoint"),
        pytest.param("spans", id="source-spans"),
        pytest.param("entries", id="xpath-entries"),
    ],
)
def test_atheris_parser_document_reports_oracle_failure(oracle: str) -> None:
    with pytest.raises(AssertionError, match=f"^{oracle} broke$"):
        document_observation(b"<p>x</p>", **{oracle: lambda _text: f"{oracle} broke"})


@pytest.mark.parametrize("target", parser_targets(), ids=lambda target: target.name)
def test_atheris_parser_callback_rejects_invalid_utf8(target: Target) -> None:
    with pytest.raises(UnicodeDecodeError):
        target.callback(b"\xff")


def test_atheris_parser_exports_have_unique_consumers() -> None:
    assert tuple((target.name, target.exports) for target in parser_targets()) == (
        ("html-document", ("turbohtml.parse", "turbohtml.Document", "turbohtml.Node")),
        (
            "html-fragment",
            (
                "turbohtml.parse_fragment",
                "turbohtml.Element",
                "turbohtml.Html",
                "turbohtml.Formatter",
                "turbohtml.Indent",
                "turbohtml.Minify",
            ),
        ),
        ("html-incremental", ("turbohtml.IncrementalParser",)),
        ("html-tokenizer", ("turbohtml.tokenize", "turbohtml.Tokenizer", "turbohtml.Token", "turbohtml.TokenType")),
    )
