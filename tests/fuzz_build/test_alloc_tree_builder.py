from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

import turbohtml
from turbohtml.rewrite import rewrite

if TYPE_CHECKING:
    from collections.abc import Callable

# duplicate and dynamic attribute names, a non-ASCII name, leading text and a misnested formatting run reach the
# attribute sink, the dynamic name table, the text copy and the open-element stack
_SEED: Final = "  x<p zq=1 zq=2 \u00e9t\u00e9=3>t</p><b><i>u</b>v<table><td>w"
# a selected option fills the select's selectedcontent cache, which the parse allocates on first use
_SELECT: Final = "<select><button><selectedcontent></selectedcontent></button><option selected>a</option></select>"


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda _: turbohtml.parse(_SEED), id="parse"),
        pytest.param(lambda _: turbohtml.parse_fragment(_SEED), id="parse-fragment"),
        pytest.param(lambda _: turbohtml.parse(_SELECT), id="parse-selectedcontent"),
        pytest.param(lambda _: turbohtml.Tokenizer(), id="tokenizer"),
        pytest.param(lambda _: rewrite(_SEED), id="rewrite"),
        pytest.param(
            lambda _: rewrite(_SEED, elements=[("[zq]", lambda element: element.set_attribute("yq", "1"))]),
            id="rewrite-custom-attributes",
        ),
    ],
)
def test_tokenizer_consumer_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], call: Callable[[object], object]
) -> None:
    assert set(alloc_sweep(call)) == {"MemoryError"}
