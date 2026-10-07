"""Fuzz builds stop super-linear XPath and XSLT work at the native operation limit instead of timing out."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable

    from turbohtml import Document

_SIBLINGS: Final = parse_xml("<r>" + "<a/>" * 100 + "</r>")
_NESTED: Final = "count(//a[count(//a[count(//a) > 0]) > 0])"
_DOUBLING: Final = parse_xml(
    '<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
    '<xsl:output method="text"/><xsl:param name="depth"/>'
    '<xsl:template match="/"><xsl:call-template name="split">'
    '<xsl:with-param name="level" select="$depth"/></xsl:call-template></xsl:template>'
    '<xsl:template name="split"><xsl:param name="level"/>'
    '<xsl:if test="$level &gt; 0">'
    '<xsl:call-template name="split"><xsl:with-param name="level" select="$level - 1"/></xsl:call-template>'
    '<xsl:call-template name="split"><xsl:with-param name="level" select="$level - 1"/></xsl:call-template>'
    '</xsl:if><xsl:if test="$level = 0">x</xsl:if></xsl:template></xsl:stylesheet>'
)


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        pytest.param(lambda: str(_SIBLINGS.xpath("count(//a[count(//a) > 0])")), "100.0", id="xpath"),
        pytest.param(lambda: Transform(_DOUBLING)(_SIBLINGS, depth="10"), "x" * 1024, id="xslt-apply"),
        pytest.param(lambda: Transform(_literal_sheet(100))(_SIBLINGS), "x" * 100, id="xslt-compile"),
    ],
)
def test_operation_limit_within_budget(run: Callable[[], str], expected: str) -> None:
    assert run() == expected


@pytest.mark.parametrize(
    ("run", "message"),
    [
        pytest.param(
            lambda: str(_SIBLINGS.xpath(_NESTED)), r"^xpath: evaluation exceeded the operation limit$", id="xpath"
        ),
        pytest.param(
            lambda: Transform(_DOUBLING)(_SIBLINGS, depth="17"),
            r"^xslt: applying the stylesheet exceeded the operation limit of \d+$",
            id="xslt-apply",
        ),
        pytest.param(
            lambda: Transform(_value_of_sheet(_NESTED))(_SIBLINGS),
            r"^xslt: expression error \(evaluation exceeded the operation limit\)$",
            id="xslt-select",
        ),
        pytest.param(
            lambda: Transform(_literal_sheet(200_000))(_SIBLINGS),
            r"^xslt: compiling the stylesheet exceeded the operation limit of \d+$",
            id="xslt-compile",
        ),
    ],
)
def test_operation_limit_stops(run: Callable[[], str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        run()


def _literal_sheet(elements: int) -> Document:
    return parse_xml(
        '<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
        f'<xsl:output method="text"/><xsl:template match="/">{"<e>x</e>" * elements}</xsl:template></xsl:stylesheet>'
    )


def _value_of_sheet(expression: str) -> Document:
    return parse_xml(
        '<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"><xsl:output method="text"/>'
        f'<xsl:template match="/"><xsl:value-of select="{expression.replace(">", "&gt;")}"/></xsl:template>'
        "</xsl:stylesheet>"
    )
