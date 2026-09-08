from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from turbohtml import Document


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        pytest.param("ul > :nth-of-type(odd)", ["a", "b", "e"], id="mixed-types"),
        pytest.param("li:nth-of-type(odd)", ["a", "e"], id="interleaved-types"),
        pytest.param("li:nth-last-of-type(odd)", ["a", "e"], id="reverse-types"),
        pytest.param("li:nth-child(odd) ~ li", ["c", "e"], id="preceding-backtrack"),
        pytest.param("li:nth-child(4n+1) ~ li", ["c", "e"], id="preceding-recount"),
        pytest.param("li:has(~ li:nth-child(odd of :scope ~ li))", ["a", "c"], id="changing-scope"),
        pytest.param("li:nth-last-child(odd of li)", ["a", "e"], id="reverse-filter"),
    ],
)
def test_nth_positions_across_query_orders(selector: str, expected: list[str]) -> None:
    document: Final[Document] = parse(
        "<ul><li>a</li><!--gap--><span>b</span><li>c</li>text<span>d</span><li>e</li></ul>"
    )
    assert [element.text for element in document.select(selector)] == expected


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        pytest.param(":nth-child(odd)", [True, False, True], id="children"),
        pytest.param(":nth-child(odd of li)", [True, False, True], id="filtered"),
    ],
)
def test_nth_positions_in_individual_matches(selector: str, expected: list[bool]) -> None:
    document: Final[Document] = parse("<ul><li>a</li><li>b</li><li>c</li></ul>")
    assert [element.matches(selector) for element in document.select("li")] == expected
