from __future__ import annotations

import pytest

from turbohtml.clean import minify_css


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(" a { background-size:cover auto; } ", "a{background-size:cover auto}", id="size-cover"),
        pytest.param(" a { background-size:contain auto; } ", "a{background-size:contain auto}", id="size-contain"),
        pytest.param(" a { background-size:inherit auto; } ", "a{background-size:inherit auto}", id="size-inherit"),
        pytest.param(" a { background-size:initial auto; } ", "a{background-size:initial auto}", id="size-initial"),
        pytest.param(" a { background-size:unset auto; } ", "a{background-size:unset auto}", id="size-unset"),
        pytest.param(" a { background-size:revert auto; } ", "a{background-size:revert auto}", id="size-revert"),
        pytest.param(
            " a { background-size:revert-layer auto; } ", "a{background-size:revert-layer auto}", id="size-revert-layer"
        ),
        pytest.param(
            " a { background-size:10px;background-size:cover auto; } ",
            "a{background-size:10px;background-size:cover auto}",
            id="size-fallback",
        ),
        pytest.param(
            " a { background-size:10px!important;background-size:cover auto!important; } ",
            "a{background-size:10px!important;background-size:cover auto!important}",
            id="size-important",
        ),
        pytest.param(" a { background-size:10px auto; } ", "a{background-size:10px}", id="size-length"),
        pytest.param(" a { background-size:10% auto; } ", "a{background-size:10%}", id="size-percent"),
        pytest.param(" a { background-size:auto auto; } ", "a{background-size:auto}", id="size-auto"),
        pytest.param(
            " a { background-size:cover auto,10px auto; } ", "a{background-size:cover auto,10px}", id="size-layers"
        ),
        pytest.param(
            " a { background-repeat:repeat-x repeat-x; } ", "a{background-repeat:repeat-x repeat-x}", id="repeat-x"
        ),
        pytest.param(
            " a { background-repeat:repeat-y repeat-y; } ", "a{background-repeat:repeat-y repeat-y}", id="repeat-y"
        ),
        pytest.param(
            " a { background-repeat:inherit inherit; } ", "a{background-repeat:inherit inherit}", id="repeat-inherit"
        ),
        pytest.param(
            " a { background-repeat:initial initial; } ", "a{background-repeat:initial initial}", id="repeat-initial"
        ),
        pytest.param(" a { background-repeat:unset unset; } ", "a{background-repeat:unset unset}", id="repeat-unset"),
        pytest.param(
            " a { background-repeat:revert revert; } ", "a{background-repeat:revert revert}", id="repeat-revert"
        ),
        pytest.param(
            " a { background-repeat:revert-layer revert-layer; } ",
            "a{background-repeat:revert-layer revert-layer}",
            id="repeat-revert-layer",
        ),
        pytest.param(
            " a { background-repeat:no-repeat;background-repeat:repeat-x repeat-x; } ",
            "a{background-repeat:no-repeat;background-repeat:repeat-x repeat-x}",
            id="repeat-fallback",
        ),
        pytest.param(" a { background-repeat:round round; } ", "a{background-repeat:round}", id="repeat-round"),
        pytest.param(" a { background-repeat:space space; } ", "a{background-repeat:space}", id="repeat-space"),
        pytest.param(" a { background-repeat:repeat repeat; } ", "a{background-repeat:repeat}", id="repeat-repeat"),
        pytest.param(
            " a { background-repeat:no-repeat no-repeat; } ", "a{background-repeat:no-repeat}", id="repeat-no-repeat"
        ),
        pytest.param(
            " a { background-repeat:repeat no-repeat; } ", "a{background-repeat:repeat-x}", id="repeat-horizontal"
        ),
        pytest.param(
            " a { background-repeat:no-repeat repeat; } ", "a{background-repeat:repeat-y}", id="repeat-vertical"
        ),
        pytest.param(
            " a { background-repeat:repeat-x repeat-x,round round; } ",
            "a{background-repeat:repeat-x repeat-x,round}",
            id="repeat-layers",
        ),
    ],
)
@pytest.mark.parametrize("repeat", [pytest.param(False, id="first"), pytest.param(True, id="second")])
def test_background_pairs(source: str, expected: str, *, repeat: bool) -> None:
    assert minify_css(minify_css(source) if repeat else source) == expected
