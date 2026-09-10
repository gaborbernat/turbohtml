"""Replacement counts code points and preserves literal NUL characters."""

from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse


@pytest.mark.parametrize(
    ("text", "search", "replacement", "expected"),
    [
        pytest.param("a" * 32768, "a" * 64 + "b" + "a" * 64, "X", "a" * 32768, id="kmp-miss"),
        pytest.param(
            ("a" * 4096 + "b" + "a" * 64 + "x") * 8,
            "a" * 64 + "b" + "a" * 64,
            "X",
            ("a" * 4032 + "Xx") * 8,
            id="kmp-sparse",
        ),
        pytest.param("a" * 32768, "a", "bb", "bb" * 32768, id="dense-one-character"),
        pytest.param("A short paragraph", "a", "A", "A short pArAgrAph", id="short-ascii"),
        pytest.param("abababa", "aba", "X", "XbX", id="non-overlapping"),
        pytest.param("abcabc", "abc", "", "", id="delete-all"),
        pytest.param("abc", "", "X", "abc", id="empty-search"),
        pytest.param("", "a", "X", "", id="empty-input"),
        pytest.param("", "", "X", "", id="both-empty"),
        pytest.param("abc", "abcd", "X", "abc", id="longer-search"),
        pytest.param("a\x00ba\x00b", "\x00b", "X", "aXaX", id="nul-search"),
        pytest.param("abab", "b", "\x00", "a\x00a\x00", id="nul-replacement"),
        pytest.param("a\x00a", "a", "\x00", "\x00\x00\x00", id="nul-retained-gap"),
        pytest.param("a\x00b", "", "X", "a\x00b", id="nul-empty-search"),
        pytest.param("é界😀é界😀", "界😀", "水", "é水é水", id="unicode-widths"),
        pytest.param("e\u0301", "é", "X", "e\u0301", id="no-normalization"),
        pytest.param("a'b\"a", "'", '"', 'a"b"a', id="quoted-bindings"),
    ],
)
def test_replace_bound_literals(text: str, search: str, replacement: str, expected: str) -> None:
    document: Final = parse("<p></p>")
    assert (
        document.xpath("str:replace($text, $search, $replacement)", text=text, search=search, replacement=replacement)
        == expected
    )
