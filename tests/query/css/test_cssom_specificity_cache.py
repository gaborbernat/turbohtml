from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Text, parse
from turbohtml.cssom import computed_style


@pytest.mark.parametrize(
    ("css", "expected"),
    [
        pytest.param(".hit,#missing{color:red}.hit{color:blue}", "blue", id="unmatched-list-alternative"),
        pytest.param(":is(.hit,#missing){color:red}.hit{color:blue}", "red", id="is-maximum-alternative"),
        pytest.param(":where(#target,.hit){color:red}div{color:blue}", "blue", id="where-zero-specificity"),
        pytest.param(".hit,#target{color:red}.hit{color:blue}", "red", id="matching-list-maximum"),
        pytest.param(".hit,#missing{color:red}.hit,#other{color:blue}", "blue", id="source-order"),
        pytest.param(":invalid-pseudo{color:red}.hit{color:blue}", "blue", id="invalid-rule-before-valid"),
        pytest.param(":invalid-pseudo{color:red}", "canvastext", id="invalid-only-sheet"),
        pytest.param("", "canvastext", id="empty-sheet"),
    ],
)
def test_computed_style_preserves_alternative_specificity(css: str, expected: str) -> None:
    document: Final = parse(f"<style>{css}</style>" + '<div class="hit" id="target"></div>' * 3)
    assert [computed_style(node)["color"] for node in document.select("div")] == [expected] * 3


def test_computed_style_keeps_specificity_within_each_sheet() -> None:
    document: Final = parse(
        '<style>#target,#missing{color:red}</style><style>.hit{color:blue}</style><div class="hit" id="target"></div>'
    )
    assert computed_style(document.select("div")[0])["color"] == "red"


def test_computed_style_rebuilds_specificity_after_selector_change() -> None:
    document: Final = parse(
        '<style>.hit,#missing{color:red}div.hit{color:blue}</style><div class="hit" id="target"></div>'
    )
    node: Final = document.select("div")[0]
    before: Final = computed_style(node)["color"]
    text: Final = document.select("style")[0].children[0]
    assert isinstance(text, Text)
    text.data = "#target{color:red}div.hit{color:blue}"
    assert (before, computed_style(node)["color"]) == ("blue", "red")
