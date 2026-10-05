from __future__ import annotations

from typing import Final

import pytest

from turbohtml.clean import minify_css

_CASES: Final = [
    pytest.param(
        "@media screen { bad; .a { opacity: 0; } }",
        "@media screen{bad;.a{opacity:0}}",
        id="media-stray",
    ),
    pytest.param(
        "@media screen { color: red; .a { opacity: 0; } }",
        "@media screen{color: red;.a{opacity:0}}",
        id="media-declaration",
    ),
    pytest.param(
        "@supports (display: grid) { bad; .a { opacity: 0; } }",
        "@supports(display:grid){bad;.a{opacity:0}}",
        id="supports",
    ),
    pytest.param(
        "@container x (width > 1px) { bad; .a { opacity: 0; } }",
        "@container x (width > 1px){bad;.a{opacity:0}}",
        id="container",
    ),
    pytest.param("@layer x { bad; .a { opacity: 0; } }", "@layer x{bad;.a{opacity:0}}", id="layer"),
    pytest.param("@keyframes x { bad; from { opacity: 0; } }", "@keyframes x{bad;0%{opacity:0}}", id="keyframes"),
    pytest.param(
        ".p { @media screen { color: red; .a { opacity: 0; } } }",
        ".p{@media screen{color: red;.a{opacity:0}}}",
        id="style-nested-media",
    ),
    pytest.param(
        "@media screen { bad; /*!keep*/ .a { opacity: 0; } }",
        "@media screen{bad;/*!keep*/.a{opacity:0}}",
        id="banner",
    ),
    pytest.param(
        "@media screen { .x { opacity: 1; } bad; .a { opacity: 0; } }",
        "@media screen{.x{opacity:1}bad;.a{opacity:0}}",
        id="after-rule",
    ),
    pytest.param(
        "@media screen { bad; @supports (display: grid) { .a { opacity: 0; } } }",
        "@media screen{bad;@supports(display:grid){.a{opacity:0}}}",
        id="before-at-rule",
    ),
    pytest.param(
        "@media screen { --x: a; .a { opacity: 0; } }",
        "@media screen{--x: a;.a{opacity:0}}",
        id="custom-property",
    ),
    pytest.param("@media screen { bad;; .a { opacity: 0; } }", "@media screen{bad;.a{opacity:0}}", id="empty-segment"),
    pytest.param("@media screen { .a { opacity: 0; } bad; }", "@media screen{.a{opacity:0}bad}", id="last-stray"),
    pytest.param("@media screen { .a { opacity: 0; } }", "@media screen{.a{opacity:0}}", id="valid-rule"),
    pytest.param(
        "@media screen { .a\\;b { opacity: 0; } }", "@media screen{.a\\;b{opacity:0}}", id="escaped-semicolon"
    ),
    pytest.param(
        '@media screen { [title=";"] { opacity: 0; } }',
        '@media screen{[title=";"]{opacity:0}}',
        id="quoted-semicolon",
    ),
    pytest.param("bad; .a { opacity: 0; }", "", id="top-level-invalid"),
    pytest.param("bad; ", "bad", id="top-level-recovery"),
]


@pytest.mark.parametrize(("source", "expected"), _CASES)
def test_group_recovery_first(source: str, expected: str) -> None:
    assert minify_css(source) == expected


@pytest.mark.parametrize(("source", "expected"), _CASES)
def test_group_recovery_repeat(source: str, expected: str) -> None:
    assert minify_css(minify_css(source)) == expected
