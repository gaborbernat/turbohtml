"""turbohtml: fast, typed HTML utilities powered by a C-accelerated core."""

from __future__ import annotations

from importlib.metadata import version

from ._html import (
    Comment,
    Doctype,
    Document,
    Element,
    Namespace,
    Node,
    Text,
    Token,
    Tokenizer,
    TokenType,
    escape,
    parse,
    parse_fragment,
    tokenize,
    unescape,
)

__version__ = version("turbohtml")
"""The installed package version."""

__all__ = [
    "Comment",
    "Doctype",
    "Document",
    "Element",
    "Namespace",
    "Node",
    "Text",
    "Token",
    "TokenType",
    "Tokenizer",
    "__version__",
    "escape",
    "parse",
    "parse_fragment",
    "tokenize",
    "unescape",
]
