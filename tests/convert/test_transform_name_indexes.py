from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize("padding", [pytest.param(1, id="small"), pytest.param(16, id="indexed")])
@pytest.mark.parametrize(
    ("declarations", "body", "expected"),
    [
        pytest.param(
            '<xsl:template name="target">first</xsl:template><xsl:template name="target">second</xsl:template>',
            '<xsl:call-template name="target"/>' * 2,
            "<out>firstfirst</out>",
            id="first-named-template",
        ),
        pytest.param(
            '<xsl:key name="target" match="p" use="@value"/><xsl:key name="target" match="q" use="@value"/>',
            "<xsl:value-of select=\"count(key('target','v'))\"/>:<xsl:value-of select=\"key('target','v')/@kind\"/>",
            "<out>1:P</out>",
            id="first-key-declaration",
        ),
        pytest.param(
            '<xsl:attribute-set name="base"><xsl:attribute name="c">3</xsl:attribute></xsl:attribute-set>'
            '<xsl:attribute-set name="target" use-attribute-sets="base">'
            '<xsl:attribute name="a">1</xsl:attribute></xsl:attribute-set>'
            '<xsl:attribute-set name="target"><xsl:attribute name="b">2</xsl:attribute></xsl:attribute-set>',
            '<item xsl:use-attribute-sets="target"/>',
            '<out><item c="3" a="1" b="2"/></out>',
            id="attribute-set-duplicates-and-chain",
        ),
        pytest.param("", '<item xsl:use-attribute-sets="missing"/>', "<out><item/></out>", id="missing-attribute-set"),
        pytest.param(
            '<xsl:key name="target" match="p" use="@value"/>',
            "<xsl:value-of select=\"count(key('target','absent'))\"/>",
            "<out>0</out>",
            id="missing-key-value",
        ),
    ],
)
def test_transform_name_indexes(
    padding: int,
    declarations: str,
    body: str,
    expected: str,
    indexed_transform: Callable[[int, str, str], Transform],
) -> None:
    transform: Final = indexed_transform(padding, declarations, body)
    assert [
        transform(parse_xml('<root><p value="v" kind="P"/><q value="v" kind="Q"/></root>')).strip() for _ in range(2)
    ] == [expected, expected]


@pytest.mark.parametrize("padding", [pytest.param(1, id="small"), pytest.param(16, id="indexed")])
@pytest.mark.parametrize(
    ("body", "message"),
    [
        pytest.param('<xsl:call-template name="missing"/>', "undeclared template", id="template"),
        pytest.param("<xsl:value-of select=\"key('missing','v')\"/>", "undeclared key", id="key"),
    ],
)
def test_transform_name_index_missing(
    padding: int, body: str, message: str, indexed_transform: Callable[[int, str, str], Transform]
) -> None:
    transform: Final = indexed_transform(padding, "", body)
    with pytest.raises(ValueError, match=message):
        transform(parse_xml("<root/>"))


def test_transform_name_index_reuse(indexed_transform: Callable[[int, str, str], Transform]) -> None:
    transform: Final = indexed_transform(
        16,
        '<xsl:key name="target" match="p" use="@value"/>'
        "<xsl:template name=\"target\"><xsl:value-of select=\"key('target','v')/@kind\"/></xsl:template>",
        '<xsl:call-template name="target"/>',
    )
    assert [transform(parse_xml(f'<root><p value="v" kind="{kind}"/></root>')).strip() for kind in ("A", "B", "A")] == [
        "<out>A</out>",
        "<out>B</out>",
        "<out>A</out>",
    ]


@pytest.fixture
def indexed_transform() -> Callable[[int, str, str], Transform]:
    def compile_transform(padding: int, declarations: str, body: str) -> Transform:
        return Transform(
            parse_xml(
                '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
                '<xsl:output method="xml" omit-xml-declaration="yes"/>'
                + "".join(
                    f'<xsl:template name="unused{index}"/>'
                    f'<xsl:key name="unused{index}" match="unused" use="@value"/>'
                    f'<xsl:attribute-set name="unused{index}"/>'
                    for index in range(padding)
                )
                + declarations
                + f'<xsl:template match="/"><out>{body}</out></xsl:template></xsl:stylesheet>'
            )
        )

    return compile_transform
