from __future__ import annotations

import json
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - Node executes the fixed benchmark corpus
from typing import TYPE_CHECKING, Final, cast

import pytest
from bench.operations import INPUTS

if TYPE_CHECKING:
    from collections.abc import Callable

_NODE: Final = shutil.which("node")
pytestmark = pytest.mark.skipif(_NODE is None, reason="node not available")


@pytest.mark.parametrize(
    ("operation", "case", "shape"),
    [
        pytest.param("minify-js-propagation", 0, (256, 2), id="propagation-interleaved"),
        pytest.param("minify-js-propagation", 1, (1, 2), id="propagation-single"),
        pytest.param("minify-js-propagation", 2, (256, 2), id="propagation-grouped"),
        pytest.param("minify-js-single-use", 0, (256, 1), id="single-use-grouped"),
        pytest.param("minify-js-single-use", 1, (256, 1), id="single-use-separated"),
        pytest.param("minify-js-single-use", 2, (1, 1), id="single-use-single"),
    ],
)
@pytest.mark.parametrize(
    ("module", "executable"),
    [
        pytest.param("bench.core", None, id="turbohtml"),
        pytest.param("bench.competitors.rjsmin", None, id="rjsmin"),
        pytest.param("bench.competitors.jsmin", None, id="jsmin"),
        pytest.param("bench.competitors.css_html_js_minify", None, id="css-html-js-minify"),
        pytest.param("bench.competitors.terser", "terser", id="terser"),
        pytest.param("bench.competitors.esbuild", "esbuild", id="esbuild"),
        pytest.param("bench.competitors.tdewolff", "minify", id="tdewolff"),
    ],
)
def test_minifiers_preserve_callback_order(
    operation: str, case: int, shape: tuple[int, int], module: str, executable: str | None
) -> None:
    if executable is not None and shutil.which(executable) is None:
        pytest.skip(f"{executable} not available")
    minify: Final = cast("Callable[[str], str]", pytest.importorskip(module).minify_js)
    source: Final = cast("str", INPUTS[operation]()[case][1])
    count, repeat = shape
    values: Final = [index % 10 if operation == "minify-js-propagation" else index for index in range(count)]
    assert (
        json.loads(
            subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed corpus and CLI arguments
                [
                    cast("str", _NODE),
                    "-e",
                    minify(source) + ";const calls=[];const result=f(value=>(calls.push(value),value));"
                    "console.log(JSON.stringify({calls,result}))",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout
        )
        == {"calls": values, "result": [value for value in values for _ in range(repeat)]}
    )


@pytest.mark.parametrize("operation", ["minify-js-propagation", "minify-js-single-use"])
@pytest.mark.parametrize("case", [0, 1, 2])
def test_minifiers_calmjs_rejects_const(operation: str, case: int) -> None:
    minify: Final = cast("Callable[[str], str]", pytest.importorskip("bench.competitors.calmjs_parse").minify_js)
    with pytest.raises(SyntaxError, match="Unexpected 'const'"):
        minify(cast("str", INPUTS[operation]()[case][1]))
