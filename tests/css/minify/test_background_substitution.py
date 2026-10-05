from __future__ import annotations

import pytest

from turbohtml.clean import minify_css


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            " a { --size:cover;background-size:10px;background-size:var(--size) auto; } ",
            "a{--size:cover;background-size:10px;background-size:var(--size)auto}",
            id="cover-computed-invalid",
        ),
        pytest.param(
            " a { --size:contain;background-size:var(--size) auto; } ",
            "a{--size:contain;background-size:var(--size)auto}",
            id="contain",
        ),
        pytest.param(
            " a { background-size:var(--missing,cover) auto; } ",
            "a{background-size:var(--missing,cover)auto}",
            id="cover-fallback",
        ),
        pytest.param(
            " a { background-size:var(--missing,contain) auto; } ",
            "a{background-size:var(--missing,contain)auto}",
            id="contain-fallback",
        ),
        pytest.param(
            " a { --size:10px;background-size:var(--size) auto; } ",
            "a{--size:10px;background-size:var(--size)auto}",
            id="length-variable",
        ),
        pytest.param(
            " a { --size:10px 20px;background-size:var(--size) auto; } ",
            "a{--size:10px 20px;background-size:var(--size)auto}",
            id="two-axis-variable",
        ),
        pytest.param(
            " a { --size:auto;background-size:var(--size) auto; } ",
            "a{--size:auto;background-size:var(--size)auto}",
            id="auto-variable",
        ),
        pytest.param(
            " a { background-size:var(--missing) auto; } ",
            "a{background-size:var(--missing)auto}",
            id="missing-variable",
        ),
        pytest.param(" a { background-size:10px auto; } ", "a{background-size:10px}", id="literal-length"),
        pytest.param(" a { background-size:calc(5px + 5px) auto; } ", "a{background-size:10px}", id="folded-math"),
        pytest.param(
            " a { background-size:var(--size) auto,var(--other,cover) auto; } ",
            "a{background-size:var(--size)auto,var(--other,cover)auto}",
            id="layers",
        ),
    ],
)
@pytest.mark.parametrize("repeat", [pytest.param(False, id="first"), pytest.param(True, id="second")])
def test_background_substitution(source: str, expected: str, *, repeat: bool) -> None:
    assert minify_css(minify_css(source) if repeat else source) == expected
