"""turbohtml: fast, typed HTML utilities powered by a C-accelerated core."""

from __future__ import annotations

from importlib.metadata import version

from ._html import (
    Axis,
    CData,
    Comment,
    Doctype,
    Document,
    Element,
    Formatter,
    Indent,
    Minify,
    Namespace,
    Node,
    ProcessingInstruction,
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
    "Axis",
    "CData",
    "Comment",
    "Doctype",
    "Document",
    "Element",
    "Formatter",
    "Indent",
    "Minify",
    "Namespace",
    "Node",
    "ProcessingInstruction",
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
