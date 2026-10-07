from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fuzz.atheris_parser_targets import (
    document_observation,
    fragment_observation,
    incremental_observation,
    parser_targets,
    token_observation,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fuzz.atheris_registry import Target


@pytest.mark.parametrize(
    "observe",
    [
        pytest.param(document_observation, id="document"),
        pytest.param(incremental_observation, id="incremental"),
    ],
)
def test_atheris_parser_document_output(observe: Callable[[bytes], str]) -> None:
    assert observe("<p>水😀</p>".encode()) == "<html><head></head><body><p>水😀</p></body></html>"


def test_atheris_parser_fragment_output() -> None:
    assert fragment_observation(b"<p>x&amp;y</p>") == "<div><p>x&amp;y</p></div>"


def test_atheris_parser_token_fields() -> None:
    assert token_observation(b'<p id="a">x</p>') == (
        ("START_TAG", "p", None, (("id", "a"),), False, 1, 0),
        ("TEXT", None, "x", None, False, 1, 10),
        ("END_TAG", "p", None, (), False, 1, 11),
    )


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
