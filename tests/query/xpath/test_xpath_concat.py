from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse


@pytest.mark.parametrize(
    "count", [pytest.param(0, id="empty"), pytest.param(1, id="one"), pytest.param(1000, id="many")]
)
@pytest.mark.parametrize(
    ("markup", "text"),
    [pytest.param("", "", id="empty-values"), pytest.param("é<b>界</b>😀", "é界😀", id="descendant-text")],
)
def test_concat_node_strings(count: int, markup: str, text: str) -> None:
    document: Final = parse("<main>" + f"<i>{markup}</i>" * count + "</main>")
    assert document.xpath("str:concat(//i)") == text * count
