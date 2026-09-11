from __future__ import annotations

from typing import Final

import pytest

from turbohtml.clean import minify_js


@pytest.mark.parametrize("count", [1, 17, 512], ids=["single", "heap", "long"])
def test_guard_chain_growth_preserves_return_order(count: int) -> None:
    source: Final = (
        "function f(x){" + "".join(f"if(x==={index})return g({index});" for index in range(count)) + "return g(-1)}"
    )
    expected: Final = "function f(a){return " + "".join(f"a==={index}?g({index}):" for index in range(count)) + "g(-1)}"
    assert minify_js(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "function f(){if(a){while(b)g()}else{while(c)h()}if(d)return 1;return 2}",
            "function f(){if(a)for(;b;)g();else for(;c;)h();return d?1:2}",
            id="preserve-else",
        ),
        pytest.param(
            "function f(){if(a)while(b)g();if(c)return 1;return 2}",
            "function f(){if(a)for(;b;)g();return c?1:2}",
            id="preserve-loop",
        ),
        pytest.param("function f() { if (a) return g(); }", "function f(){if(a)return g()}", id="last-guard"),
        pytest.param("function f(){if(a)return 1;return}", "function f(){if(a)return 1}", id="void-return"),
    ],
)
def test_guard_chain_growth_preserves_unfolded_statements(source: str, expected: str) -> None:
    assert minify_js(source) == expected
