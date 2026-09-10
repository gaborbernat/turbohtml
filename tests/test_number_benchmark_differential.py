from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

_LXML: Final = pytest.importorskip("bench.competitors.lxml", exc_type=ImportError)


@pytest.mark.parametrize("attribute", ["count", "from"])
def test_number_benchmark_lxml_current_pattern_unsupported(attribute: str) -> None:
    sheet, source = cast("tuple[str, str]", INPUTS["transform-number"]()[21][1])
    with pytest.raises(NotImplementedError, match=r"XSLT 1\.0 forbids current\(\) in patterns"):
        _LXML.transform((sheet.replace('count="', f'{attribute}="'), source))


def test_number_benchmark_lxml_current_expression() -> None:
    sheet: Final = (
        '<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
        '<xsl:output method="text"/><xsl:template match="/"><xsl:for-each select="root/p">'
        '<xsl:number count="p"/><xsl:text>:</xsl:text><xsl:value-of select="current()/@id"/>'
        "</xsl:for-each></xsl:template></xsl:stylesheet>"
    )
    assert str(_LXML.transform((sheet, '<root><p id="7"/></root>'))) == "1:7"
