from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

import turbohtml
from turbohtml import XPath
from turbohtml.transform import Transform, strparam

if TYPE_CHECKING:
    from collections.abc import Callable

# a number past 2^53 converts through CPython's strtod, which allocates
_LONG_NUMBER: Final = "123456789012345678901234567890.5"
_SOURCE: Final = (
    f'<r> <i n="2">a</i> <i n="1">b</i> <i n="3">c</i> <v n="{_LONG_NUMBER}">{_LONG_NUMBER}</v> '
    f'<v n="{_LONG_NUMBER}1">{_LONG_NUMBER}1</v> </r>'
)
# paths, predicates, a union and string functions grow every parser and evaluator buffer
_EXPRESSION: Final = (
    "//i[@n > 1 and contains(., 'a')] | //i[last()]/following-sibling::* | "
    "//r/i[position() = 2][concat(substring-before('a-b', '-'), normalize-space(' x  y ')) != '']"
)
_XSL: Final = '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
_VALUE_OF: Final = (
    f'{_XSL}<xsl:output method="text"/><xsl:param name="value"/><xsl:template match="/">'
    '<xsl:value-of select="$value"/></xsl:template></xsl:stylesheet>'
)
# every compiled-expression site: keys, a global variable, a sort, a test, an attribute value template, xsl:number,
# format-number, copy-of, a named template with a parameter, and match patterns on elements and attributes; the
# priority and the numeric sort keys convert long numbers, and whitespace stripping detaches the source's blank text
_STYLESHEET: Final = (
    f'{_XSL}<xsl:strip-space elements="*"/><xsl:key name="k" match="i" use="@n"/><xsl:param name="p" select="1"/>'
    '<xsl:variable name="v" select="count(//i)"/><xsl:template match="/"><out>'
    '<xsl:for-each select="//i"><xsl:sort select="@n" data-type="number" order="descending"/>'
    '<xsl:if test="position() &gt; 0"><e a="{@n}"><xsl:value-of select="concat(., $p, $v)"/><xsl:number/></e>'
    "</xsl:if></xsl:for-each><xsl:apply-templates select=\"key('k', 2)\"/>"
    '<xsl:call-template name="t"><xsl:with-param name="x" select="string(//i[1])"/></xsl:call-template>'
    '<xsl:for-each select="//v"><xsl:sort select="@n" data-type="number"/><xsl:sort select="." data-type="number"/>'
    '<xsl:sort select="string(.)" data-type="number"/><xsl:number value="//i[1]/@n"/></xsl:for-each>'
    '<xsl:value-of select="format-number(//i[1]/@n, \'0.0\')"/><xsl:copy-of select="//i[2]"/></out></xsl:template>'
    f'<xsl:template match="i" priority="{_LONG_NUMBER}">'
    '<m><xsl:copy><xsl:apply-templates select="@*"/></xsl:copy></m></xsl:template>'
    '<xsl:template match="@n"><xsl:attribute name="z"><xsl:value-of select="."/></xsl:attribute></xsl:template>'
    '<xsl:template name="t"><xsl:param name="x"/><xsl:element name="t{1 + 1}">'
    "<xsl:value-of select=\"translate($x, 'a', 'b')\"/></xsl:element></xsl:template></xsl:stylesheet>"
)


def _xml(source: str) -> turbohtml.Document:
    # a fresh document per run, so the compiled-expression cache of one run cannot skip the parser in the next
    document = turbohtml.parse_xml(source)
    document.serialize()  # copy the parsed text out of the input now, so the sweep fails only the query engines
    return document


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda document: document.xpath(_EXPRESSION), id="xpath"),
        pytest.param(lambda document: document.xpath_one("string(//i[2])"), id="xpath-one"),
        pytest.param(
            lambda document: XPath("(//i | //v)[position() <= $limit]")(document, limit=2), id="compiled-xpath"
        ),
        pytest.param(lambda document: document.xpath("sum(//i/@n) div count(//i)"), id="xpath-number"),
        pytest.param(lambda document: document.xpath(f"-//i[1]/@n + number(//v) * {_LONG_NUMBER}"), id="long-number"),
        pytest.param(lambda document: document.xpath("//i[. = //v or @n > //v]"), id="node-set-number"),
    ],
)
def test_xpath_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], call: Callable[[turbohtml.Document], object]
) -> None:
    assert set(alloc_sweep(call, lambda: _xml(_SOURCE))) == {"MemoryError"}


@pytest.mark.parametrize(
    "stylesheet",
    [
        pytest.param(_VALUE_OF, id="value-of-select"),
        pytest.param(_STYLESHEET, id="every-expression"),
    ],
)
def test_xslt_compile_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], stylesheet: str
) -> None:
    assert set(alloc_sweep(lambda document: Transform(document, allow_imports=False), lambda: _xml(stylesheet))) == {
        "MemoryError"
    }


@pytest.mark.parametrize(
    ("stylesheet", "source", "params"),
    [
        pytest.param(_VALUE_OF, "<root/>", {"value": strparam("a\"b'c")}, id="parameter-expression"),
        pytest.param(_STYLESHEET, _SOURCE, {"p": "'q'"}, id="every-expression"),
    ],
)
def test_xslt_apply_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], stylesheet: str, source: str, params: dict[str, str]
) -> None:
    compiled = Transform(_xml(stylesheet), allow_imports=False)
    assert set(alloc_sweep(lambda document: compiled(document, **params), lambda: _xml(source))) == {"MemoryError"}
