from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml.clean import minify_css

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

_POSITION_STRINGS: Final[list[ParameterSet]] = [
    pytest.param('left "x" .5px', 'left "x" .5px', id="string-offset"),
    pytest.param('left "0" .5px', 'left "0" .5px', id="numeric-string"),
    pytest.param('"left" top', '"left" top', id="quoted-keyword"),
    pytest.param('left "" .5px', 'left "" .5px', id="empty-string"),
    pytest.param("left 'x' .5px", "left 'x' .5px", id="single-quotes"),
    pytest.param('left /**/"x"/**/ .5px', 'left "x" .5px', id="comments"),
    pytest.param('left "x" .5px!important', 'left "x" .5px!important', id="priority"),
    pytest.param('right bottom,left "x" .5px', 'right bottom,left "x" .5px', id="later-layer"),
    pytest.param('left "x" .5px,right bottom', 'left "x" .5px,right bottom', id="first-layer"),
    pytest.param('left "x" .5px,right "y" top', 'left "x" .5px,right "y" top', id="both-layers"),
    pytest.param("left top", "0 0", id="valid-keywords"),
    pytest.param("left 0 top .5px", "0 .5px", id="valid-offsets"),
    pytest.param("right bottom,left top", "100% 100%,0 0", id="valid-layers"),
    pytest.param("calc(10% + 1px) center", "calc(10% + 1px)", id="valid-function"),
]


@pytest.mark.parametrize(("value", "expected"), _POSITION_STRINGS)
def test_minify_css_background_position_strings(value: str, expected: str) -> None:
    assert minify_css(f"a{{background-position:{value}}}") == f"a{{background-position:{expected}}}"


@pytest.mark.parametrize(("value", "expected"), _POSITION_STRINGS)
def test_minify_css_background_position_strings_are_a_fixed_point(value: str, expected: str) -> None:
    assert minify_css(minify_css(f"a{{background-position:{value}}}")) == f"a{{background-position:{expected}}}"


@pytest.mark.parametrize(("value", "expected"), _POSITION_STRINGS)
def test_minify_css_background_position_strings_preserve_cascade(value: str, expected: str) -> None:
    assert minify_css(f"a{{background-position:10px 20px;background-position:{value}}}") == (
        f"a{{background-position:10px 20px;background-position:{expected}}}"
    )
