from __future__ import annotations

from typing import Final

import pytest

from turbohtml.clean import minify_css


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "a { --p:25% 75%; background-position:var(--p) center; }",
            "a{--p:25% 75%;background-position:var(--p)center}",
            id="known-two-percent",
        ),
        pytest.param(
            "a { background-position:var(--missing,25% 75%) center; }",
            "a{background-position:var(--missing,25% 75%)center}",
            id="fallback-two-percent",
        ),
        pytest.param(
            "a { --p:left top; background-position:var(--p) 50%; }",
            "a{--p:left top;background-position:var(--p)50%}",
            id="known-two-keywords",
        ),
        pytest.param(
            "a { background-position:var(--missing,left top) 50%; }",
            "a{background-position:var(--missing,left top)50%}",
            id="fallback-two-keywords",
        ),
        pytest.param(
            "a { --p:left; background-position:center var(--p); }",
            "a{--p:left;background-position:center var(--p)}",
            id="known-horizontal-keyword",
        ),
        pytest.param(
            "a { background-position:center var(--missing,left); }",
            "a{background-position:center var(--missing,left)}",
            id="fallback-horizontal-keyword",
        ),
        pytest.param(
            "a { background-position:10% center,var(--p) center; }",
            "a{background-position:10% center,var(--p)center}",
            id="layered-variable",
        ),
        pytest.param(
            "a { background-position:env(missing-position,25% 75%) center; }",
            "a{background-position:env(missing-position,25% 75%)center}",
            id="environment-fallback-control",
        ),
        pytest.param(
            "a { background-position:calc(var(--p)) center; }",
            "a{background-position:calc(var(--p))center}",
            id="opaque-calculation-control",
        ),
        pytest.param(
            "a { background-position:calc(10% + 20%) center; }",
            "a{background-position:30%}",
            id="folded-scalar-control",
        ),
        pytest.param(
            "a { background-position:10% center; }", "a{background-position:10%}", id="literal-percent-control"
        ),
        pytest.param(
            "a { background-position:left top; }", "a{background-position:0 0}", id="literal-keywords-control"
        ),
        pytest.param(
            "a { background-position:var(--p); }", "a{background-position:var(--p)}", id="one-component-control"
        ),
    ],
)
def test_position_substitutions(source: str, expected: str) -> None:
    first: Final = minify_css(source)
    assert (first, minify_css(first)) == (expected,) * 2
