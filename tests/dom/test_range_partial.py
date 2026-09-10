from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element, Range


@pytest.mark.parametrize("extract", [False, True], ids=["clone", "extract"])
def test_range_partial_excludes_siblings(*, extract: bool) -> None:
    root: Final = Element("div")
    root.set_inner_html('<section data-x="é水😀">abcdef' + "<i></i>" * 100 + "</section>tail")
    boundary: Final = Range(root)
    boundary.set_end(root.children[0].children[0], 3)
    result: Final = boundary.extract_contents() if extract else boundary.clone_contents()
    assert result.html == '<section data-x="é水😀">abc</section>'
