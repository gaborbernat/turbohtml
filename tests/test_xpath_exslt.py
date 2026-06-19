"""EXSLT regular-expression functions ``re:test`` and ``re:replace``.

parsel and scrapy enable the EXSLT regexp namespace by default and lean on
``re:test`` in predicates, so turbohtml dispatches the ``re:`` prefix to Python's
re module. lxml needs the namespace registered; the prefix is built in here.
"""

from __future__ import annotations

import re

import pytest

import turbohtml
from turbohtml import Element

HTML = "<html><body><a href='/path/123'>a</a><a href='HTTP://x'>b</a><a href='/y'>c</a></body></html>"


def tags(result: list[Element | str]) -> list[str]:
    return [node.tag if isinstance(node, Element) else node for node in result]


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("//a[re:test(@href, '[0-9]+')]", ["a"], id="digits"),
        pytest.param("//a[re:test(@href, '^/')]", ["a", "a"], id="anchored"),
        pytest.param("//a[re:test(@href, 'NOPE')]", [], id="no-match"),
        pytest.param("//a[re:test(@href, 'http', 'i')]", ["a"], id="case-insensitive-flag"),
        pytest.param("//a[re:test(@href, 'http')]", [], id="case-sensitive-default"),
    ],
)
def test_re_test(doc: turbohtml.Node, expr: str, expected: list[str]) -> None:
    assert tags(doc.xpath(expr)) == expected


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("re:replace('hello world', 'o', 'g', '0')", "hell0 w0rld", id="global"),
        pytest.param("re:replace('aaa', 'a', '', 'b')", "baa", id="first-only-default"),
        pytest.param("re:replace('Hello', 'hello', 'i', 'hi')", "hi", id="case-insensitive"),
        pytest.param("re:replace('abc', 'X', 'imsxz', 'Y')", "abc", id="all-flag-letters-no-match"),
        pytest.param("re:replace('a.b', 'a.b', 's', 'Z')", "Z", id="dotall-flag"),
    ],
)
def test_re_replace(doc: turbohtml.Node, expr: str, expected: str) -> None:
    assert doc.xpath(expr) == expected


def test_re_test_global_flag_is_accepted(doc: turbohtml.Node) -> None:
    # 'g' is meaningless for a boolean test, but must be tolerated, not rejected.
    assert doc.xpath("re:test('a', 'a', 'g')") is True


def test_re_test_malformed_pattern_propagates_python_error(doc: turbohtml.Node) -> None:
    with pytest.raises(re.error):
        doc.xpath("//a[re:test(@href, '(')]")


def test_re_replace_malformed_pattern_propagates_python_error(doc: turbohtml.Node) -> None:
    with pytest.raises(re.error):
        doc.xpath("re:replace('x', '(', '', 'y')")
