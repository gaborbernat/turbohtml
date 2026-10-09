from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

import turbohtml
from turbohtml import Html, Minify
from turbohtml.clean import JSMinify, minify_js

if TYPE_CHECKING:
    from collections.abc import Callable

# Destructuring targets, arrow and function parameter lists, and a parenthesized optional chain reach the parser's
# early-error walks; unused, single-use, literal and shadowing bindings reach the compress and mangle passes; a string
# concatenation, a separated BigInt and a 70-digit number reach the fold and print buffers, and an escaped name the
# identifier decoder.
_SCRIPT: Final[str] = (
    f"var long_name = 1, s = 'a' + 'b', big = 1_000n, wide = {'1' * 70}, \\u0061bc = 0; console.log(long_name + 2);"
    "function f(alpha, [beta, {gamma = 1, ...rest}], ...more) { const unused = alpha; let x = [1, , 3];"
    " if (alpha) { return !0 } else { return beta ? gamma : rest } } function p() { const c = 5; return c + c }"
    "var g = (p, q) => p + q, h = async function* () { yield* g(1, 2) }, o = (a?.b).c;"
    "class K { static s = 1; get v() { return this.s } m() { return typeof k == 'undefined' } }"
    "for (const [k, v] of Object.entries({a: 1, b: 2})) { label: while (k) { break label } }"
    "try { f(1) } catch ({message}) { x = `t${message}u` } new K().m(), void 0;"
)
_PAGE: Final[str] = f"<p>x</p><script>{_SCRIPT}</script><script type=module>let m = 1; m++</script>"
_MINIFY_JS: Final[Html] = Html(layout=Minify(minify_js=JSMinify()))


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: minify_js("var a = 1"), id="declaration"),
        pytest.param(lambda: minify_js("function f(long_name) { return long_name + 1 }"), id="mangle"),
        pytest.param(lambda: minify_js("[a, b, c, d] = [1, 2, 3, 4]"), id="assignment-pattern"),
        pytest.param(lambda: minify_js("var [a, b, c, d, e, f, g, h] = i"), id="binding-pattern"),
        pytest.param(lambda: minify_js(_SCRIPT), id="script"),
        pytest.param(lambda: minify_js(_SCRIPT, JSMinify(fold=False, mangle=False)), id="parse-only"),
        # the empty statements fill the fuzz build's node arena to a doubling, so the sequence node the fold pass
        # allocates for the merged calls takes the failed growth
        pytest.param(lambda: minify_js(";;;;;a(); b(); c();"), id="fold-allocation"),
    ],
)
def test_js_minify_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], call: Callable[[], object]
) -> None:
    assert set(alloc_sweep(lambda _: call())) == {"MemoryError"}


def test_html_js_minify_allocation_failure_raises_memory_error(alloc_sweep: Callable[..., list[str]]) -> None:
    assert set(alloc_sweep(lambda document: document.serialize(_MINIFY_JS), _page)) == {"MemoryError"}


def _page() -> turbohtml.Document:
    document = turbohtml.parse(_PAGE)
    document.serialize()  # copy the parsed text out of the input now, so the sweep fails only the minifier
    return document
