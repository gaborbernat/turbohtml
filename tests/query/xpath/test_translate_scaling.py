from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml


@pytest.mark.parametrize(
    ("source", "target", "text", "expected"),
    [
        pytest.param("abcdefghijklmnop", "ABCDEFGHIJKLMNOP", "apz" * 64, "APz" * 64, id="map-and-miss"),
        pytest.param("abcdefghijklmnop", "A", "apz" * 64, "Az" * 64, id="delete"),
        pytest.param("a" * 16, "ABCDEFGHIJKLMNOP", "a" * 64, "A" * 64, id="first-duplicate"),
        pytest.param("雪" * 16, "𐀀", "雪z" * 64, "𐀀z" * 64, id="wide-unicode"),
        pytest.param("abcdefghijklmnop", "", "a" * 64, "", id="delete-all"),
        pytest.param("abcdefghijklmno", "A", "az" * 64, "Az" * 64, id="short-map"),
        pytest.param("abcdefghijklmnop", "A", "a" * 63, "A" * 63, id="short-text"),
        pytest.param("abcdefghijklmnop", "A", "a" * 64, "A" * 64, id="threshold"),
        pytest.param("", "A", "a" * 64, "a" * 64, id="empty-map"),
        pytest.param("abcdefghijklmnop", "A", "", "", id="empty-text"),
        pytest.param(
            "".join(chr(256 + index * 128) for index in range(16)),
            "A" * 16,
            chr(256 + 15 * 128) * 64,
            "A" * 64,
            id="hash-collisions",
        ),
    ],
)
def test_translate_character_map(source: str, target: str, text: str, expected: str) -> None:
    document: Final = parse_xml(f"<root>{text}</root>")
    assert document.xpath(f"translate(string(/root), '{source}', '{target}')") == expected
