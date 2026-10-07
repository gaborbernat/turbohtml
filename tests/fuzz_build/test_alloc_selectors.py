from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

import turbohtml

if TYPE_CHECKING:
    from collections.abc import Callable

# three compounds, two arms, a forgiving :is() list and a relative :has() argument grow every parser buffer; the
# tag-subject selectors build the document's element index
_SELECTOR: Final = "main > p[zq] a, :is(b, i, [zq]) :has(> a)"


def _document() -> turbohtml.Document:
    # a fresh document per run, so the compiled-selector cache of one run cannot skip the parser in the next
    return turbohtml.parse("<!DOCTYPE html><main><p zq=1><a>t</a><b>u</b></p></main>")


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda document: document.select(_SELECTOR), id="select"),
        pytest.param(lambda document: document.select_one(_SELECTOR), id="select-one"),
        pytest.param(lambda document: document.select("b"), id="select-tag-index"),
        pytest.param(lambda document: document.select("p b"), id="select-index"),
        pytest.param(lambda document: document.select_one("p b"), id="select-one-index"),
        pytest.param(lambda document: document.find_all("b"), id="find-all-index"),
    ],
)
def test_selector_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], call: Callable[[turbohtml.Document], object]
) -> None:
    assert set(alloc_sweep(call, _document)) == {"MemoryError"}
