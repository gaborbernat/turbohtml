from __future__ import annotations

from typing import Final

import pytest

from turbohtml.clean import minify_js


@pytest.mark.parametrize("count", [2, 1000], ids=["small", "long"])
@pytest.mark.parametrize("nested", [False, True], ids=["calls", "sequences"])
def test_sequence_growth_preserves_call_order(count: int, *, nested: bool) -> None:
    expressions: Final = [f"f({index}),g({index})" if nested else f"f({index})" for index in range(count)]
    assert minify_js(";".join(expressions)) == ",".join(expressions)
