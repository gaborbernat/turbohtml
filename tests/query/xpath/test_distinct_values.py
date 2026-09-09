from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Document, parse_xml


@pytest.mark.parametrize("unique", [pytest.param(1, id="identical"), pytest.param(64, id="many-values")])
def test_distinct_retains_first_occurrences(unique: int) -> None:
    document: Final[Document] = parse_xml(
        "<root>" + "".join(f'<item id="{index}">value-{index % unique}</item>' for index in range(256)) + "</root>"
    )
    assert document.xpath("set:distinct(//item)/@id") == [str(index) for index in range(unique)]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param('<item id="a"/><item id="b"/>', ["a"], id="empty"),
        pytest.param('<item id="a">é😀</item><item id="b">é😀</item>', ["a"], id="unicode"),
        pytest.param('<item id="a">a<b>b</b></item><item id="b">ab</item>', ["a"], id="descendants"),
        pytest.param("", [], id="empty-set"),
        pytest.param('<item id="a">one</item>', ["a"], id="singleton"),
    ],
)
def test_distinct_string_values(content: str, expected: list[str]) -> None:
    assert parse_xml(f"<root>{content}</root>").xpath("set:distinct(//item)/@id") == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param('<item a="é" b="😀"/><item a="é" b=""/>', ["é", "😀", ""], id="duplicates"),
        pytest.param('<item a="é"/>', ["é"], id="singleton"),
    ],
)
def test_distinct_attribute_values(content: str, expected: list[str]) -> None:
    assert parse_xml(f"<root>{content}</root>").xpath("set:distinct(//item/@*)") == expected
