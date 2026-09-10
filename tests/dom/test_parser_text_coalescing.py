from __future__ import annotations

from typing import Final

import pytest

from turbohtml import IncrementalParser, parse


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("a", id="ascii"),
        pytest.param("é", id="latin1"),
        pytest.param("名", id="ucs2"),
        pytest.param("😀", id="ucs4"),
    ],
)
@pytest.mark.parametrize("locations", [pytest.param(False, id="no-locations"), pytest.param(True, id="locations")])
def test_parser_text_coalescing_keeps_one_node_across_feeds(text: str, *, locations: bool) -> None:
    parser: Final = IncrementalParser(source_locations=locations)
    parser.feed("<p>")
    for _ in range(129):
        parser.feed(text)
    parser.feed("</p>")
    paragraph: Final = parser.close().find("p")
    assert paragraph is not None
    assert [node.text for node in paragraph.children] == [text * 129]


def test_parser_text_coalescing_switches_between_nodes() -> None:
    source: Final = "<p>" + "x</missing>" * 40 + "<i>" + "y</missing>" * 40 + "</i>" + "z</missing>" * 40 + "</p>"
    paragraph: Final = parse(source).find("p")
    assert paragraph is not None
    assert [node.text for node in paragraph.children] == ["x" * 40, "y" * 40, "z" * 40]


def test_parser_text_coalescing_keeps_fostered_text_before_table() -> None:
    root: Final = parse("<div><table>" + "x<tr><td>cell</td></tr>" * 40 + "</table></div>").find("div")
    assert root is not None
    assert [node.text for node in root.children] == ["x" * 40, "cell" * 40]
