from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse


@pytest.mark.parametrize("element_root", [pytest.param(False, id="document"), pytest.param(True, id="element")])
def test_nested_candidates_keep_link_density(*, element_root: bool) -> None:
    document: Final = parse(
        "<main>"
        + "".join(
            f'<div id="candidate-{index}" class="{"article" if index == 32 else ""}">'
            '<p>A sentence with enough prose, and a clause, to score. <a href="/">linked words</a></p>'
            "<!--gap--><img><script>ignored</script><svg><text>ignored</text></svg>"
            for index in range(64)
        )
        + "</div>" * 64
        + "</main>"
    )
    assert (document.select("#candidate-0")[0] if element_root else document).main_content() == document.select(
        "#candidate-32"
    )[0]


def test_many_link_only_candidates_have_no_main_content() -> None:
    document: Final = parse(
        "<main>"
        + '<section><p><a href="/">A linked sentence with enough text to score.</a></p></section>' * 64
        + "</main>"
    )
    assert document.main_content() is None
