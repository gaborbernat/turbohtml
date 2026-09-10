"""Translation indexes must preserve the first mapping and removal rules."""

from __future__ import annotations

from string import ascii_lowercase, ascii_uppercase
from typing import Final

import pytest

from turbohtml import parse


@pytest.mark.parametrize(
    ("text", "source", "target", "expected"),
    [
        pytest.param("a" * 32768, ascii_lowercase, ascii_uppercase, "A" * 32768, id="first-map-entry"),
        pytest.param("b" * 32768, ascii_lowercase, ascii_uppercase, "B" * 32768, id="second-map-entry"),
        pytest.param("a" * 64, "a" * 65536, "X", "X" * 64, id="duplicate-first-entry"),
        pytest.param("a" * 64, "a" * 65536, "", "", id="duplicate-first-removal"),
        pytest.param(
            "yz" * 64 + "a", "abcdefghijklmnopaa", "ABCDEFGHIJKLMNOPXY", "yz" * 64 + "A", id="duplicate-after-index"
        ),
        pytest.param(
            "yz" * 64 + "界😀", "abcdefghijklmnop界😀", "ABCDEFGHIJKLMNOPé", "yz" * 64 + "é", id="unicode-after-index"
        ),
        pytest.param("a" * 128 + "z", ascii_lowercase, "A", "A" * 128, id="late-removal"),
        pytest.param("yz" * 64, "", "X", "yz" * 64, id="empty-map"),
        pytest.param("", ascii_lowercase, "A", "", id="empty-input"),
    ],
)
def test_translate_deferred_index(text: str, source: str, target: str, expected: str) -> None:
    document: Final = parse("<p></p>")
    assert document.xpath(f"translate('{text}', '{source}', '{target}')") == expected


def test_translate_nul_mapping() -> None:
    document: Final = parse("<p></p>")
    assert (
        document.xpath(
            "translate($text, $source, $target)",
            text="yz" * 64 + "\x00a",
            source="abcdefghijklmnop\x00",
            target="ABCDEFGHIJKLMNOP!",
        )
        == "yz" * 64 + "!A"
    )
