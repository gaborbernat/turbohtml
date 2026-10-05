from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml.clean import minify_css

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

_MATH_CASES: Final[list[ParameterSet]] = [
    pytest.param("a { width:calc(1px+ 2em) }", "a{width:calc(1px+ 2em)}", id="missing-left-space"),
    pytest.param(
        "a { width:calc(1px/**/+ 2em + 2em) }", "a{width:calc(1px/**/+ 2em + 2em)}", id="comment-instead-of-left-space"
    ),
    pytest.param("a { width:9px;width:calc(1px+ 2em) }", "a{width:9px;width:calc(1px+ 2em)}", id="earlier-valid-width"),
    pytest.param(
        "a { width:9px;width:calc(1px/**/+ 2em + 2em) }",
        "a{width:9px;width:calc(1px/**/+ 2em + 2em)}",
        id="earlier-valid-width-comment",
    ),
    pytest.param("a { width:calc(1px +(2px)) }", "a{width:calc(1px +(2px))}", id="missing-right-space"),
    pytest.param("a { width:calc(1px +/**/2px) }", "a{width:calc(1px +/**/2px)}", id="comment-instead-of-right-space"),
    pytest.param("a { width:calc(1px/**/- 2em) }", "a{width:calc(1px/**/- 2em)}", id="minus-without-left-space"),
    pytest.param("a { width:calc(+ 1px) }", "a{width:calc(+ 1px)}", id="operator-at-start"),
    pytest.param("a { width:calc( + 1px) }", "a{width:calc(+ 1px)}", id="leading-space-before-operator"),
    pytest.param("a { width:calc(1px -) }", "a{width:calc(1px -)}", id="operator-at-end"),
    pytest.param(
        "a { width:calc(1px+ calc(2px + 3px)) }", "a{width:calc(1px+ calc(2px + 3px))}", id="outer-invalid-nested-valid"
    ),
    pytest.param(
        "a { width:calc(1px + calc(2px+ 3px)) }", "a{width:calc(1px + calc(2px+ 3px))}", id="outer-valid-nested-invalid"
    ),
    pytest.param("a { width:calc(var(--x)+ 2px) }", "a{width:calc(var(--x)+ 2px)}", id="opaque-variable-missing-space"),
    pytest.param("a { width:calc(var(--x) + 2px) }", "a{width:calc(var(--x) + 2px)}", id="opaque-variable-valid-space"),
    pytest.param("a { width:calc(1px /**/+ 2em) }", "a{width:calc(1px + 2em)}", id="real-left-space-before-comment"),
    pytest.param("a { width:calc(1px +/**/ 2em) }", "a{width:calc(1px + 2em)}", id="real-right-space-after-comment"),
    pytest.param("a { width:calc(1px/**/ + 2em) }", "a{width:calc(1px + 2em)}", id="real-left-space-after-comment"),
    pytest.param("a { width:calc(1px + 2px) }", "a{width:3px}", id="valid-sum"),
    pytest.param("a { width:calc(3px - 2px) }", "a{width:1px}", id="valid-difference"),
    pytest.param("a { width:calc(1px*2) }", "a{width:2px}", id="valid-product"),
    pytest.param("a { width:calc(1px/2) }", "a{width:.5px}", id="valid-division"),
    pytest.param("a { width:min(1px+ 2em,3px) }", "a{width:min(1px+ 2em,3px)}", id="other-math-function"),
    pytest.param("a { width:f(1px/**/+ 2em) }", "a{width:f(1px + 2em)}", id="nonmath-body-unchanged"),
    pytest.param(
        "a { width:calc(1px+ </**//style) }", "a{width:calc(1px+ </**//style)}", id="synthetic-space-inside-span"
    ),
    pytest.param("a { width:calc(1px+ 2em", "a{width:calc(1px+ 2em)}", id="eof-numeric-unit"),
    pytest.param("a { width:calc(1px+ 2", "a{width:calc(1px+ 2)}", id="eof-number"),
    pytest.param("a { width:max(1px+ 2em,3px) }", "a{width:max(1px+ 2em,3px)}", id="maximum-missing-space"),
    pytest.param("a { width:clamp(0px,1px+ 2em,3px) }", "a{width:clamp(0px,1px+ 2em,3px)}", id="clamp-missing-space"),
    pytest.param("a { width:calc(1px+ 2em ", "a{width:calc(1px+ 2em )}", id="eof-whitespace"),
    pytest.param("a { width:calc(1px+ 2em/**/", "a{width:calc(1px+ 2em/**/)}", id="eof-comment"),
]


@pytest.mark.parametrize(("source", "expected"), _MATH_CASES)
def test_minify_css_math_operator_whitespace(source: str, expected: str) -> None:
    assert minify_css(source) == expected


@pytest.mark.parametrize(("source", "expected"), _MATH_CASES)
def test_minify_css_math_operator_whitespace_fixed_point(source: str, expected: str) -> None:
    assert minify_css(minify_css(source)) == expected
