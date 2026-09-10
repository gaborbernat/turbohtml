from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("source", "instructions", "rules", "expected"),
    [
        pytest.param(
            "<root><p " + " ".join(f'a{index}="{index}"' for index in range(96)) + "/></root>",
            '<xsl:apply-templates select="root/p/@*"/>' * 2,
            "".join(f'<xsl:template match="@a{index}">{index}|</xsl:template>' for index in range(96)),
            "".join(f"{index}|" for index in range(96)) * 2,
            id="many-attribute-rules",
        ),
        pytest.param(
            "<root><p/></root>",
            (
                '<xsl:apply-templates select="root/p"/>'
                + "".join(f'<xsl:apply-templates select="root/p" mode="view{index}"/>' for index in range(64))
                + '<xsl:apply-templates select="root/p"/>'
            )
            * 2,
            '<xsl:template match="p">default|</xsl:template>'
            + "".join(f'<xsl:template match="p" mode="view{index}">{index}|</xsl:template>' for index in range(64)),
            ("default|" + "".join(f"{index}|" for index in range(64)) + "default|") * 2,
            id="many-named-and-default-modes",
        ),
        pytest.param(
            "<root>" + "<p/>" * 40 + "</root>",
            '<xsl:apply-templates select="root/p"/>' * 2,
            '<xsl:template match="p">X</xsl:template>',
            "X" * 80,
            id="growing-cache",
        ),
        pytest.param(
            "<root><p/></root>",
            '<xsl:apply-templates select="root/p"/>'
            '<xsl:apply-templates select="root/p" mode="m"/>'
            '<xsl:apply-templates select="root/p" mode="n"/>'
            '<xsl:apply-templates select="root/p" mode="m"/>'
            '<xsl:apply-templates select="root/p"/>',
            '<xsl:template match="p">D</xsl:template>'
            '<xsl:template match="p" mode="m">M</xsl:template>'
            '<xsl:template match="p" mode="n">N</xsl:template>',
            "DMNMD",
            id="mode-content-and-default",
        ),
        pytest.param(
            '<root><p a="1" b="2"/></root>',
            '<xsl:apply-templates select="root/p/@*"/>' * 2,
            '<xsl:template match="@a">A<xsl:value-of select="."/></xsl:template>'
            '<xsl:template match="@b">B<xsl:value-of select="."/></xsl:template>',
            "A1B2A1B2",
            id="attribute-indices",
        ),
        pytest.param(
            "<root><p>A<b>B</b><!--ignored--></p></root>",
            '<xsl:apply-templates select="root/p"/>' * 2,
            "",
            "ABAB",
            id="cached-builtin-misses",
        ),
        pytest.param(
            '<root><p a="A" b="B"/></root>',
            '<xsl:apply-templates select="root/p/@*"/>' * 2,
            "",
            "ABAB",
            id="cached-attribute-misses",
        ),
        pytest.param(
            "<root><p/><p/></root>",
            '<xsl:apply-templates select="root/p"/>' * 2,
            '<xsl:template match="p" priority="1">L</xsl:template>'
            '<xsl:template match="p" priority="2">H</xsl:template>',
            "HHHH",
            id="priority",
        ),
        pytest.param(
            "<root><p/><q/></root>",
            '<xsl:apply-templates select="root/*"/>' * 2,
            '<xsl:template match="p|q">A</xsl:template><xsl:template match="p|q">B</xsl:template>',
            "BBBB",
            id="union-and-position-tie",
        ),
    ],
)
def test_transform_rule_cache(
    source: str,
    instructions: str,
    rules: str,
    expected: str,
    cached_transform: Callable[[str, str], Transform],
) -> None:
    transform: Final = cached_transform(instructions, rules)
    assert [transform(parse_xml(source)) for _ in range(2)] == [expected, expected]


def test_transform_rule_cache_reuse(cached_transform: Callable[[str, str], Transform]) -> None:
    transform: Final = cached_transform(
        '<xsl:apply-templates select="root/p"/>' * 2,
        '<xsl:template match="p"><xsl:value-of select="."/></xsl:template>',
    )
    assert [transform(parse_xml(f"<root><p>{value}</p></root>")) for value in ("first", "second", "first")] == [
        "firstfirst",
        "secondsecond",
        "firstfirst",
    ]


@pytest.fixture
def cached_transform() -> Callable[[str, str], Transform]:
    def compile_transform(instructions: str, rules: str) -> Transform:
        return Transform(
            parse_xml(
                '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
                '<xsl:output method="text"/>'
                + "".join(f'<xsl:template match="unused{index}"/>' for index in range(16))
                + f'<xsl:template match="/">{instructions}</xsl:template>{rules}</xsl:stylesheet>'
            )
        )

    return compile_transform
