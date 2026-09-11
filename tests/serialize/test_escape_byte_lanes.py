from __future__ import annotations

import html
from typing import Final

import pytest

from turbohtml import escape


@pytest.mark.parametrize("quote", [False, True], ids=["text", "quoted"])
@pytest.mark.parametrize("offset", range(8), ids=lambda value: f"offset-{value}")
@pytest.mark.parametrize(
    "pair",
    [
        pytest.param("&'", id="amp-apostrophe"),
        pytest.param("'&", id="apostrophe-amp"),
        pytest.param("<=", id="less-equals"),
        pytest.param("=<", id="equals-less"),
        pytest.param(">?", id="greater-question"),
        pytest.param("?>", id="question-greater"),
        pytest.param('"#', id="quote-hash"),
        pytest.param('#"', id="hash-quote"),
        pytest.param("\xa6\xa7", id="high-bits"),
        pytest.param("&\x00", id="embedded-null"),
    ],
)
def test_escape_adjacent_byte_lanes(pair: str, offset: int, *, quote: bool) -> None:
    text: Final = "x" * offset + pair * 8 + "tail"
    assert escape(text, quote=quote) == html.escape(text, quote=quote)
