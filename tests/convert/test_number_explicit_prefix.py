"""Explicit prefix counts retain zero values and reset boundaries across visits."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("source", "patterns", "visits", "expected"),
    [
        pytest.param(
            "<root><p/><q/><p/></root>",
            'count="p"',
            (0, 3, 0, 1, 2, 0, 3),
            "0|2|0|1|1|0|2|",
            id="cached-document-root-zero",
        ),
        pytest.param(
            "<root><q/><p/><q/><section/><p/><q/><section/><q/></root>",
            'count="p" from="section"',
            (8, 1, 5, 4, 2, 7, 3, 6, 8),
            "0|0|1|0|1|0|1|1|0|",
            id="reverse-zero-reset-then-forward",
        ),
        pytest.param(
            "<root><q/><p/><q/><section/><p/><q/><section/><q/></root>",
            'count="p" from="section"',
            (1, 1, 2, 3, 4, 5, 6, 7, 8),
            "0|0|1|1|0|1|1|0|0|",
            id="repeated-zero-before-index",
        ),
        pytest.param(
            "<root><p/><q/><p/></root>",
            'count="absent"',
            (3, 1, 2, 3),
            "0|0|0|0|",
            id="empty-count-set",
        ),
        pytest.param(
            "<root><p/><q/><p/></root>",
            'count="p" from="absent"',
            (3, 1, 2, 3),
            "2|1|1|2|",
            id="empty-from-set",
        ),
        pytest.param(
            "<root><p/><p/><q/><p/></root>",
            'count="p" from="p"',
            (4, 1, 3, 2, 4),
            "1|1|1|1|1|",
            id="count-from-overlap",
        ),
        pytest.param(
            "<root><p/><q/><p/></root>",
            'count="*"',
            (1, 3, 2, 3),
            "2|4|3|4|",
            id="wildcard-includes-root",
        ),
        pytest.param(
            "<root><p/><q/><p/><section/><p/><q/></root>",
            'from="section"',
            (1, 3, 5, 2, 6, 4, 5),
            "1|2|1|1|1|1|1|",
            id="default-count-name-changes",
        ),
        pytest.param(
            "<root><p/><long/><p/><section/><long/></root>",
            'from="section"',
            (1, 3, 2, 5, 1),
            "1|2|1|1|1|",
            id="default-count-name-length-changes",
        ),
        pytest.param(
            "<root>a<!--a-->b<!--b--><section/>c<!--c--></root>",
            'from="section"',
            (1, 3, 2, 4, 6, 7, 1),
            "1|2|1|2|1|1|1|",
            id="default-count-node-kind-changes",
        ),
        pytest.param(
            '<root><p category="a"/><p category="b"/><p category="a"/></root>',
            'count="p[@category=current()/@category]"',
            (3, 1, 2, 3),
            "2|1|1|2|",
            id="dynamic-count-fallback",
        ),
        pytest.param(
            "<root><p/><q/><p/></root>",
            'count="p" from="q[true()]"',
            (1, 3, 2, 3),
            "1|1|0|1|",
            id="predicate-from-fallback",
        ),
    ],
)
def test_number_explicit_prefix_visits(
    source: str,
    patterns: str,
    visits: tuple[int, ...],
    expected: str,
    explicit_prefix_transform: Callable[[str, tuple[int, ...]], Transform],
) -> None:
    transform: Final = explicit_prefix_transform(patterns, visits)
    assert [transform(parse_xml(source)) for _ in range(2)] == [expected, expected]


def test_number_explicit_prefix_document_reuse(
    explicit_prefix_transform: Callable[[str, tuple[int, ...]], Transform],
) -> None:
    transform: Final = explicit_prefix_transform('count="p" from="section"', (1, 3, 2, 3))
    assert [
        transform(parse_xml(source))
        for source in (
            "<root><p/><p/><p/></root>",
            "<root><q/><section/><p/></root>",
            "<root><p/><section/><q/></root>",
        )
    ] == ["1|3|2|3|", "0|1|0|1|", "1|0|0|0|"]


@pytest.fixture
def explicit_prefix_transform() -> Callable[[str, tuple[int, ...]], Transform]:
    def compile_number(patterns: str, visits: tuple[int, ...]) -> Transform:
        return Transform(
            parse_xml(
                '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
                '<xsl:output method="text"/><xsl:template match="/">'
                + "".join(
                    f'<xsl:for-each select="{"/" if index == 0 else f"root/node()[{index}]"}">'
                    '<xsl:call-template name="number"/></xsl:for-each>'
                    for index in visits
                )
                + '</xsl:template><xsl:template name="number">'
                f'<xsl:number level="any" {patterns}/><xsl:text>|</xsl:text>'
                "</xsl:template></xsl:stylesheet>"
            )
        )

    return compile_number
