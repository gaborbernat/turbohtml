"""Incremental public entry points must preserve the one-shot result."""

from __future__ import annotations

from typing import Final, NamedTuple

from turbohtml import (
    Document,
    Element,
    Formatter,
    Html,
    IncrementalParser,
    Indent,
    Minify,
    Node,
    Token,
    Tokenizer,
    TokenType,
    parse,
    parse_fragment,
    tokenize,
)

from .atheris_registry import Target

__all__ = [
    "document_observation",
    "fragment_observation",
    "incremental_observation",
    "parser_targets",
    "token_observation",
]


def parser_targets() -> tuple[Target, ...]:
    """Keep document and fragment grammar contexts distinct."""
    return (
        Target(
            "html-document",
            _document,
            ("turbohtml.parse", "turbohtml.Document", "turbohtml.Node"),
            (UnicodeDecodeError,),
        ),
        Target(
            "html-fragment",
            _fragment,
            (
                "turbohtml.parse_fragment",
                "turbohtml.Element",
                "turbohtml.Html",
                "turbohtml.Formatter",
                "turbohtml.Indent",
                "turbohtml.Minify",
            ),
            (UnicodeDecodeError,),
        ),
        Target("html-incremental", _incremental, ("turbohtml.IncrementalParser",), (UnicodeDecodeError,)),
        Target(
            "html-tokenizer",
            _tokens,
            ("turbohtml.tokenize", "turbohtml.Tokenizer", "turbohtml.Token", "turbohtml.TokenType"),
            (UnicodeDecodeError,),
        ),
    )


def _document(data: bytes) -> None:
    document_observation(data)


def _fragment(data: bytes) -> None:
    fragment_observation(data)


def _incremental(data: bytes) -> None:
    incremental_observation(data)


def _tokens(data: bytes) -> None:
    token_observation(data)


def document_observation(data: bytes) -> str:
    """Exercise returned document records through serialization consumers."""
    document: Final = parse(data.decode("utf-8"))
    _require("Document result type", condition=isinstance(document, (Document, Node)))
    return _serialization(document)


def fragment_observation(data: bytes) -> str:
    """Grammar fragments use a div context rather than document insertion modes."""
    fragment: Final = parse_fragment(data.decode("utf-8"), "div")
    _require("Fragment result type", condition=isinstance(fragment, Element))
    return _serialization(fragment)


def incremental_observation(data: bytes) -> str:
    """Empty feeds and multibyte boundaries must preserve the complete parse."""
    data.decode("utf-8")
    parser: Final = IncrementalParser()
    parser.feed(b"")
    for value in data:
        parser.feed(bytes((value,)))
        parser.feed(b"")
    document: Final = parser.close()
    observed: Final = _serialization(document)
    _require("Incremental document differs", condition=observed == parse(data).serialize())
    return observed


def token_observation(data: bytes) -> tuple[_TokenSnapshot, ...]:
    """Streaming and reset must preserve token fields and source positions."""
    source: Final = data.decode("utf-8")
    tokenizer: Final = Tokenizer()
    streamed: Final = list(tokenizer.feed(""))
    for char in source:
        streamed.extend(tokenizer.feed(char))
        streamed.extend(tokenizer.feed(""))
    streamed.extend(tokenizer.close())
    observed: Final = tuple(_token_snapshot(token) for token in streamed)
    _require(
        "Incremental tokens differ", condition=observed == tuple(_token_snapshot(token) for token in tokenize(source))
    )
    tokenizer.reset()
    _require(
        "Reset tokens differ",
        condition=tuple(_token_snapshot(token) for token in tokenizer.feed(source))
        + tuple(_token_snapshot(token) for token in tokenizer.close())
        == observed,
    )
    return observed


def _serialization(node: Node) -> str:
    for formatter in Formatter:
        for layout in (None, Indent(2)):
            options: Final = Html(formatter=formatter, layout=layout)
            rendered: Final = node.serialize(options)
            _require("Iterator serialization differs", condition="".join(node.serialize_iter(options)) == rendered)
            _require(
                "Encoded serialization differs", condition=node.encode("utf-8", options) == rendered.encode("utf-8")
            )
    minified_options: Final = Html(layout=Minify())
    _require(
        "Minified encoding differs",
        condition=node.encode("utf-8", minified_options) == node.serialize(minified_options).encode("utf-8"),
    )
    return node.serialize()


def _token_snapshot(token: Token) -> _TokenSnapshot:
    _require("Token result type", condition=isinstance(token, Token))
    _require("Token kind type", condition=isinstance(token.type, TokenType))
    return _TokenSnapshot(
        token.type.name,
        token.tag,
        token.data,
        tuple(token.attrs) if token.attrs is not None else None,
        token.self_closing,
        token.line,
        token.col,
    )


def _require(message: str, *, condition: bool) -> None:
    if not condition:
        raise AssertionError(message)


class _TokenSnapshot(NamedTuple):
    kind: str
    tag: str | None
    data: str | None
    attrs: tuple[tuple[str, str], ...] | None
    self_closing: bool
    line: int
    col: int
