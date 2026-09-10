from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse


@pytest.mark.parametrize("count", [pytest.param(1, id="one"), pytest.param(1000, id="many")])
def test_id_node_values_preserve_order(count: int) -> None:
    document: Final = parse(
        '<main><b id="first"></b><b id="second"></b>' + "<i> second  first second </i>" * count + "</main>"
    )
    assert document.xpath("id(//i)/@id") == ["first", "second"]
