from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

import turbohtml
from turbohtml import Html, Minify
from turbohtml.clean import CSSMinify, minify_css, minify_css_inline

if TYPE_CHECKING:
    from collections.abc import Callable

# One stylesheet that walks the engine's buffers: merged box and font shorthands, calc() and color folds, a legacy
# filter, a unicode-range list, adjacent @media blocks that join, a nested rule, and more than 32 rules so the rule
# merge builds its hash table.
_RULES: Final[str] = "".join(f".r{index}{{color:#ffffff;margin:0 0 0 0}}" for index in range(40))
_STYLESHEET: Final[str] = (
    '@charset "utf-8";'
    ".a{margin-top:1px;margin-right:2px;margin-bottom:1px;margin-left:2px;color:rgb(255,0,0);"
    "width:calc(100% - 2*10px);font-family:'Times New Roman',serif;"
    "filter:progid:DXImageTransform.Microsoft.Alpha(Opacity=80);"
    "background:url('x.png') no-repeat;transform:rotate(calc(0.5turn));color:rgb(calc(255),0,0)}"
    ".b{color:red}.a{padding:0 0 0 0}"
    "@media screen{.c{z-index:calc(1 + 2)}}@media screen{.d{font-weight:bold}}"
    "@font-face{unicode-range:U+0025-00FF,u+4??}"
    ".e{&:hover{color:hsl(120deg 100% 50% / 50%)}--custom: { a } ;flex:1 1 0%}"
    f"{_RULES}"
)
# one selector repeated with a new property each time, so each merge re-renders a longer body into the pool
_MERGES: Final[str] = "".join(f".m{{margin-{side}:{index}px}}" for index, side in enumerate(["top", "left"] * 12))
# enough declarations that the dedup table outgrows its stack slots
_DECLARATIONS: Final[str] = ";".join(f"--p{index}:{index}px" for index in range(300)) + ";color:#ff0000;margin:0 0 0 0"
_PAGE: Final[str] = f"<style>{_STYLESHEET}</style><p style='margin:0 0 0 0;color:#ff0000'>x</p>"
_MINIFY_CSS: Final[Html] = Html(layout=Minify(minify_css=CSSMinify()))


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: minify_css(".a{color:red}"), id="one-rule"),
        pytest.param(lambda: minify_css(".a{margin:0 0 0 0}"), id="one-shorthand"),
        pytest.param(lambda: minify_css_inline("color:red;margin:0 0 0 0"), id="short-inline"),
        pytest.param(lambda: minify_css(_STYLESHEET), id="stylesheet"),
        pytest.param(lambda: minify_css_inline(_DECLARATIONS), id="inline"),
        pytest.param(lambda: minify_css(".\\31 x{color:red}.y{content:'open"), id="spelled"),
        pytest.param(lambda: minify_css(_MERGES), id="merges"),
    ],
)
def test_css_minify_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], call: Callable[[], object]
) -> None:
    assert set(alloc_sweep(lambda _: call())) == {"MemoryError"}


def test_html_css_minify_allocation_failure_raises_memory_error(alloc_sweep: Callable[..., list[str]]) -> None:
    assert set(alloc_sweep(lambda document: document.serialize(_MINIFY_CSS), _page)) == {"MemoryError"}


def _page() -> turbohtml.Document:
    document = turbohtml.parse(_PAGE)
    document.serialize()  # copy the parsed text out of the input now, so the sweep fails only the minifier
    return document
