from __future__ import annotations

from typing import Final

import pytest

from turbohtml.clean import minify_css


@pytest.mark.parametrize(
    "namespace", [pytest.param("", id="fragment"), pytest.param('@namespace url("urn:svg");', id="default-namespace")]
)
@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        pytest.param("*|*:is(*.a)", "*|*:is(*.a)", id="is-class"),
        pytest.param("*|*:where(*.a)", "*|*:where(*.a)", id="where-class"),
        pytest.param("*|*:not(*.a)", "*|*:not(*.a)", id="not-class"),
        pytest.param("*|*:is(*[x])", "*|*:is(*[x])", id="attribute"),
        pytest.param("*|*:is(.b, *.a)", "*|*:is(.b,*.a)", id="later-arm"),
        pytest.param("*|*:is(.b > *.a)", "*|*:is(.b>*.a)", id="child-subject"),
        pytest.param("*|*:is(*.b *.a)", "*|*:is(*.b *.a)", id="descendant-subject"),
        pytest.param("*|*:is(:not(*.a))", "*|*:is(:not(*.a))", id="nested"),
        pytest.param("*|*:is(/**/ *.a)", "*|*:is(*.a)", id="leading-trivia"),
        pytest.param("*|*:is(*.a), *.b", "*|*:is(*.a),.b", id="top-level-after-function"),
        pytest.param("*|*:has(> *.a)", "*|*:has(>*.a)", id="relative-control"),
        pytest.param(":future(.b, *.a)", ":future(.b,*.a)", id="opaque-function"),
        pytest.param("[x='('] *.a", "[x='('] .a", id="attribute-string-parenthesis"),
        pytest.param("[x=()] *.a", "[x=()] .a", id="attribute-delimiter-parenthesis"),
        pytest.param("*.a", ".a", id="top-level-shortening"),
        pytest.param(".b > *.a", ".b>.a", id="top-level-child"),
        pytest.param("*|*.a", "*|*.a", id="qualified-star"),
        pytest.param(".a*.b", ".a*.b", id="misplaced-star"),
        pytest.param(") *.a", ") .a", id="unmatched-close"),
    ],
)
def test_functional_universal_roles(namespace: str, selector: str, expected: str) -> None:
    source: Final = f"{namespace} {selector} {{ color : red }}"
    prefix: Final = '@namespace"urn:svg";' if namespace else ""
    first: Final = minify_css(source)
    assert (first, minify_css(first)) == (f"{prefix}{expected}{{color:red}}",) * 2
