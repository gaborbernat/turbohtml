"""Equivalent numbering instructions preserve pattern boundaries and dynamic contexts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("patterns", "expected"),
    [
        pytest.param(
            ('count="p"',) * 8,
            "1," * 8 + "|" + "2," * 8 + "|" + "3," * 8 + "|",
            id="eight-equal-counts",
        ),
        pytest.param(
            ('count="p" from="section"',) * 8,
            "1," * 8 + "|" + "2," * 8 + "|" + "1," * 8 + "|",
            id="eight-equal-counts-and-froms",
        ),
        pytest.param(
            ('from="section"',) * 8,
            "1," * 8 + "|" + "2," * 8 + "|" + "1," * 8 + "|",
            id="eight-equal-froms",
        ),
        pytest.param(
            ('count="p"', 'count="q"', 'count="p"'),
            "1,0,1,|2,1,2,|3,1,3,|",
            id="different-count-content-same-length",
        ),
        pytest.param(
            ('count="p"', 'count="long"', 'count="p"'),
            "1,0,1,|2,0,2,|3,1,3,|",
            id="different-count-lengths",
        ),
        pytest.param(
            ('count="p" from="section"', 'count="p" from="missing"', 'count="p" from="section"'),
            "1,1,1,|2,2,2,|1,3,1,|",
            id="different-from-content-same-length",
        ),
        pytest.param(
            ('count="p" from="section"', 'count="p" from="root"', 'count="p" from="section"'),
            "1,1,1,|2,2,2,|1,3,1,|",
            id="different-from-lengths",
        ),
        pytest.param(
            ('count="p"', 'count="p[@cat=current()/@cat]"', 'count="p"'),
            "1,1,1,|2,2,2,|3,1,3,|",
            id="dynamic-count-between-static-counts",
        ),
        pytest.param(
            (
                'count="p" from="section"',
                'count="p" from="section[@cat != current()/@cat]"',
                'count="p" from="section"',
            ),
            "1,1,1,|2,2,2,|1,3,1,|",
            id="dynamic-from-between-static-froms",
        ),
        pytest.param(
            ('count="absent"', 'count="absent"', 'count="p"', 'count="absent"', 'count="absent"'),
            "0,0,1,0,0,|0,0,2,0,0,|0,0,3,0,0,|",
            id="equal-empty-sets-after-replacement",
        ),
        pytest.param(
            ('count=" p "', 'count=" p "', 'count="p"', 'count=" p "'),
            "1,1,1,1,|2,2,2,2,|3,3,3,3,|",
            id="equal-whitespace-and-distinct-slices",
        ),
        pytest.param(
            ('count="p"', 'count="p|q"', 'count="p"'),
            "1,1,1,|2,3,2,|3,4,3,|",
            id="union-between-static-counts",
        ),
    ],
)
def test_number_matcher_content(
    patterns: tuple[str, ...], expected: str, content_transform: Callable[[tuple[str, ...]], Transform]
) -> None:
    transform: Final = content_transform(patterns)
    source: Final = (
        '<root><section cat="a"/><p cat="a"/><q cat="b"/><p cat="a"/><long/><section cat="b"/><p cat="b"/></root>'
    )
    assert [transform(parse_xml(source)) for _ in range(2)] == [expected, expected]


@pytest.fixture
def content_transform() -> Callable[[tuple[str, ...]], Transform]:
    def compile_patterns(patterns: tuple[str, ...]) -> Transform:
        return Transform(
            parse_xml(
                '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
                '<xsl:output method="text"/><xsl:template match="/"><xsl:for-each select="root/p">'
                + "".join(f'<xsl:number level="any" {pattern}/><xsl:text>,</xsl:text>' for pattern in patterns)
                + "<xsl:text>|</xsl:text></xsl:for-each></xsl:template></xsl:stylesheet>"
            )
        )

    return compile_patterns
