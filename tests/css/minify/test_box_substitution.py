from __future__ import annotations

import pytest

from turbohtml.clean import minify_css


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            " a{--side:1px 2px 3px;margin:9px;margin:var(--side) var(--side)} ",
            "a{--side:1px 2px 3px;margin:9px;margin:var(--side)var(--side)}",
            id="margin-two-multi-value",
        ),
        pytest.param(
            " a{--side:1px 2px;padding:var(--side) var(--side) var(--side) var(--side)} ",
            "a{--side:1px 2px;padding:var(--side)var(--side)var(--side)var(--side)}",
            id="padding-four-multi-value",
        ),
        pytest.param(
            " a{--side:1px 2px 3px;margin:var(--side) 1px var(--side) 1px} ",
            "a{--side:1px 2px 3px;margin:var(--side)1px var(--side)1px}",
            id="mixed-functions",
        ),
        pytest.param(
            " a{--side:1px 2px 3px;margin:var(--side) var(--side) var(--side)} ",
            "a{--side:1px 2px 3px;margin:var(--side)var(--side)var(--side)}",
            id="margin-three-multi-value",
        ),
        pytest.param(" a{margin:var(--side)} ", "a{margin:var(--side)}", id="single-function"),
        pytest.param(" a{margin:1px 2px 1px 2px} ", "a{margin:1px 2px}", id="literal-quad"),
        pytest.param(" a{padding:calc(5px + 5px) calc(5px + 5px)} ", "a{padding:10px}", id="folded-math"),
        pytest.param(
            " a{margin:var(--missing,1px 2px 3px) var(--missing,1px 2px 3px)} ",
            "a{margin:var(--missing,1px 2px 3px)var(--missing,1px 2px 3px)}",
            id="fallback-multi-value",
        ),
        pytest.param(
            " a{padding:env(safe-area-inset-top) env(safe-area-inset-top)} ",
            "a{padding:env(safe-area-inset-top)env(safe-area-inset-top)}",
            id="environment-function",
        ),
        pytest.param(
            " a{margin:var(--side) 1px 1px 1px} ", "a{margin:var(--side)1px 1px 1px}", id="function-position-1"
        ),
        pytest.param(
            " a{margin:1px var(--side) 1px 1px} ", "a{margin:1px var(--side)1px 1px}", id="function-position-2"
        ),
        pytest.param(
            " a{margin:1px 1px var(--side) 1px} ", "a{margin:1px 1px var(--side)1px}", id="function-position-3"
        ),
        pytest.param(
            " a{margin:1px 1px 1px var(--side)} ", "a{margin:1px 1px 1px var(--side)}", id="function-position-4"
        ),
    ],
)
@pytest.mark.parametrize("repeat", [pytest.param(False, id="first"), pytest.param(True, id="second")])
def test_box_substitution(source: str, expected: str, *, repeat: bool) -> None:
    assert minify_css(minify_css(source) if repeat else source) == expected
