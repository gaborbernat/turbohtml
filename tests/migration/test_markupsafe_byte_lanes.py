from __future__ import annotations

from typing import Final

import pytest

from turbohtml.migration.markupsafe import escape


@pytest.mark.parametrize("offset", range(8), ids=lambda value: f"offset-{value}")
@pytest.mark.parametrize(
    ("pair", "escaped"),
    [
        pytest.param("&'", "&amp;&#39;", id="amp-apostrophe"),
        pytest.param("'&", "&#39;&amp;", id="apostrophe-amp"),
        pytest.param("<=", "&lt;=", id="less-equals"),
        pytest.param("=<", "=&lt;", id="equals-less"),
        pytest.param(">?", "&gt;?", id="greater-question"),
        pytest.param("?>", "?&gt;", id="question-greater"),
        pytest.param('"#', "&#34;#", id="quote-hash"),
        pytest.param('#"', "#&#34;", id="hash-quote"),
        pytest.param("\xa6\xa7", "\xa6\xa7", id="high-bits"),
        pytest.param("&\x00", "&amp;\x00", id="embedded-null"),
    ],
)
def test_escape_adjacent_byte_lanes(pair: str, escaped: str, offset: int) -> None:
    prefix: Final = "x" * offset
    assert str(escape(prefix + pair * 8 + "tail")) == prefix + escaped * 8 + "tail"
