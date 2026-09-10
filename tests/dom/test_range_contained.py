from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element, Range


@pytest.mark.parametrize("extract", [False, True], ids=["clone", "extract"])
def test_range_contained_interval(*, extract: bool) -> None:
    root: Final = Element("div")
    root.set_inner_html("".join(f"<i>{index}</i>" for index in range(100)))
    boundary: Final = Range(root, 10)
    boundary.set_end(root, 90)
    result: Final = boundary.extract_contents() if extract else boundary.clone_contents()
    assert result.html == "".join(f"<i>{index}</i>" for index in range(10, 90))
