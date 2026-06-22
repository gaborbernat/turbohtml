"""EXSLT ``str:`` string functions built into the XPath engine.

``str:replace`` (literal, non-regex), ``str:concat``, ``str:padding``, and
``str:align`` dispatch through the ``str:`` prefix without registering a namespace.
The node-set-producing ``str:tokenize`` / ``str:split`` are intentionally absent:
the engine's node-sets reference existing tree nodes and cannot synthesize tokens.
"""

from __future__ import annotations

import pytest

import turbohtml

HTML = "<div id='nums'><n>3</n><n>1</n><n>5</n><n>5</n></div>"


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("str:replace('abcabc', 'b', 'X')", "aXcaXc", id="replace-each"),
        pytest.param("str:replace('abc', 'z', 'y')", "abc", id="replace-no-match"),
        pytest.param("str:replace('abx', 'xy', 'Z')", "abx", id="replace-multichar-runs-off-tail"),
        pytest.param("str:replace('aaa', 'a', 'bb')", "bbbbbb", id="replace-grow"),
        pytest.param("str:replace('abcabc', 'bc', '')", "aa", id="replace-shrink"),
        pytest.param("str:replace('abc', '', 'X')", "abc", id="replace-empty-search"),
        pytest.param("str:replace('', 'x', 'y')", "", id="replace-empty-input"),
        pytest.param("str:concat(//n)", "3155", id="concat-nodeset"),
        pytest.param("str:concat(//absent)", "", id="concat-empty"),
        pytest.param("str:padding(5)", "     ", id="padding-default-space"),
        pytest.param("str:padding(3, 'ab')", "aba", id="padding-cycles-pattern"),
        pytest.param("str:padding(3, '')", "   ", id="padding-empty-pattern-is-spaces"),
        pytest.param("str:padding(0)", "", id="padding-zero"),
        pytest.param("str:padding(-2)", "", id="padding-negative"),
        pytest.param("str:align('ab', 'XXXXX')", "abXXX", id="align-left-default"),
        pytest.param("str:align('ab', 'XXXXX', 'right')", "XXXab", id="align-right"),
        pytest.param("str:align('ab', 'XXXXX', 'center')", "XabXX", id="align-center"),
        pytest.param("str:align('ab', 'XXXXX', 'bogus')", "abXXX", id="align-unknown-is-left"),
        pytest.param("str:align('abcdef', 'XXX')", "abc", id="align-truncate-left"),
        pytest.param("str:align('abcdef', 'XXX', 'right')", "def", id="align-truncate-right"),
    ],
)
def test_str_functions(doc: turbohtml.Node, expr: str, expected: str) -> None:
    assert doc.xpath(expr) == expected


def test_str_concat_non_nodeset_argument_raises(doc: turbohtml.Node) -> None:
    with pytest.raises(NotImplementedError, match="non-node-set"):
        doc.xpath("str:concat('x')")
