"""Number patterns retain their behavior across changing contexts and documents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("source", "select", "instructions", "expected"),
    [
        pytest.param("<root><p/><q/><p/></root>", "root/*", '<xsl:number level="any" count="p"/>', "1|1|2|", id="name"),
        pytest.param(
            "<root><p/><q/><p/></root>", "root/*", '<xsl:number level="any" count="*"/>', "2|3|4|", id="wildcard"
        ),
        pytest.param(
            "<root><p/><p/></root>", "root/p", '<xsl:number level="any" count="missing"/>', "0|0|", id="empty-count"
        ),
        pytest.param(
            "<root><p/><p/></root>",
            "root/p",
            '<xsl:number level="any" count="p" from="missing"/>',
            "1|2|",
            id="empty-from",
        ),
        pytest.param(
            "<root><p/><p/></root>",
            "root/p",
            '<xsl:number level="any" count="p" from="p"/>',
            "1|1|",
            id="count-from-overlap",
        ),
        pytest.param(
            "<root><section><p/><p/></section><section><p/></section></root>",
            "//p",
            '<xsl:number level="any" count="p" from="section"/>',
            "1|2|1|",
            id="section-reset",
        ),
        pytest.param(
            "<root><section><p/><p/></section><section><p/></section></root>",
            "//p",
            '<xsl:number count="p" from="section"/>',
            "1|2|1|",
            id="single",
        ),
        pytest.param(
            "<root><p><p/><p/></p></root>",
            "//p",
            '<xsl:number level="multiple" count="p" format="1.1"/>',
            "1|1.1|1.2|",
            id="multiple",
        ),
        pytest.param(
            '<root><p id="1"/><p id="2"/><p id="3"/></root>',
            "root/p",
            '<xsl:sort select="@id" data-type="number" order="descending"/><xsl:number level="any" count="p"/>',
            "3|2|1|",
            id="reverse",
        ),
        pytest.param(
            "<root><p/><p/></root>",
            "root/p",
            '<xsl:number level="any" count="p"/>' * 8,
            "11111111|22222222|",
            id="same-node-eight-instructions",
        ),
        pytest.param(
            "<root><p/><q/><p/></root>",
            "root/*",
            '<xsl:number level="any" count="p"/><xsl:text>/</xsl:text>'
            '<xsl:number level="any" count="q"/><xsl:text>/</xsl:text><xsl:number level="any" count="p"/>',
            "1/0/1|1/1/1|2/1/2|",
            id="count-slot-replacement",
        ),
        pytest.param(
            "<root><section><p/><p/></section><section><p/></section></root>",
            "//p",
            '<xsl:number level="any" count="p" from="section"/><xsl:text>/</xsl:text>'
            '<xsl:number level="any" count="p" from="root"/>',
            "1/1|2/2|1/3|",
            id="from-slot-replacement",
        ),
        pytest.param(
            '<root><p cat="a"/><p cat="b"/><p cat="a"/></root>',
            "root/p",
            '<xsl:number level="any" count="p[@cat=current()/@cat]"/>',
            "1|1|2|",
            id="dynamic-count",
        ),
        pytest.param(
            '<root><section key="a"><p cat="a"/></section><section key="b"><p cat="b"/></section>'
            '<section key="a"><p cat="a"/></section></root>',
            "//p",
            '<xsl:number level="any" count="p" from="section[@key=current()/@cat]"/>',
            "1|1|1|",
            id="dynamic-from",
        ),
        pytest.param(
            '<root><p cat="a"/><p cat="b"/><p cat="a"/></root>',
            "root/p",
            '<xsl:number level="any" count="p"/><xsl:text>/</xsl:text>'
            '<xsl:number level="any" count="p[@cat=current()/@cat]"/><xsl:text>/</xsl:text>'
            '<xsl:number level="any"/>',
            "1/1/1|2/1/2|3/2/3|",
            id="static-dynamic-default-interleaving",
        ),
        pytest.param(
            "<root><p/><q/><p/></root>", "root/*", '<xsl:number level="any" count="p|q"/>', "1|2|3|", id="union"
        ),
        pytest.param("<root><p/><p/></root>", "root/p", '<xsl:number level="any" count="root/p"/>', "1|2|", id="path"),
        pytest.param("<root><p/><p/></root>", "root/p", '<xsl:number level="any" count=" / "/>', "1|1|", id="document"),
        pytest.param(
            "<root><p/><p/></root>", "root/p", '<xsl:number level="any" count="/root/p"/>', "1|2|", id="absolute-child"
        ),
        pytest.param(
            "<root><p/><p/></root>",
            "root/p",
            """<xsl:number level="any" count="id('missing')"/>""",
            "0|0|",
            id="function-root",
        ),
        pytest.param(
            "<root><p/><p/></root>",
            "root/p",
            """<xsl:number level="any" count="id('missing')/p"/>""",
            "0|0|",
            id="expression-root",
        ),
        pytest.param(
            "<root><p/><p/></root>", "root/p", '<xsl:number level="any" count=" //p "/>', "1|2|", id="absolute-trimmed"
        ),
        pytest.param(
            "<root><p/>text<p/></root>",
            "root/p",
            '<xsl:number level="any" count="text()"/>',
            "0|1|",
            id="text-test",
        ),
        pytest.param(
            '<root><p id="a"/><p id="b"/></root>',
            "root/p/@id",
            '<xsl:number level="any" count="p"/>',
            "1|1|",
            id="attribute-context",
        ),
        pytest.param(
            "<root><p/><p/></root>",
            "root/p",
            '<xsl:number level="any" count="p" value="7"/>',
            "7|7|",
            id="value-bypass",
        ),
    ],
)
def test_number_matcher_contexts(
    source: str, select: str, instructions: str, expected: str, matcher_transform: Callable[[str, str, str], Transform]
) -> None:
    transform: Final = matcher_transform(select, instructions, "")
    assert [transform(parse_xml(source)) for _ in range(2)] == [expected, expected]


def test_number_matcher_reused_documents(matcher_transform: Callable[[str, str, str], Transform]) -> None:
    transform: Final = matcher_transform("root/*", '<xsl:number level="any" count="p"/>', "")
    assert [
        transform(parse_xml(source)) for source in ("<root><p/><p/></root>", "<root><q/></root>", "<root><p/></root>")
    ] == [
        "1|2|",
        "0|",
        "1|",
    ]


def test_number_matcher_whitespace_restore(matcher_transform: Callable[[str, str, str], Transform]) -> None:
    transform: Final = matcher_transform(
        "root/node()", '<xsl:number level="any" count="p"/>', '<xsl:strip-space elements="*"/>'
    )
    document: Final = parse_xml("<root> <p/> <p/> </root>")
    assert (
        [transform(document) for _ in range(2)],
        matcher_transform("root/node()", '<xsl:number level="any" count="p"/>', "")(document),
    ) == (["1|2|", "1|2|"], "0|1|1|2|2|")


@pytest.mark.parametrize("attribute", ["count", "from"])
@pytest.mark.parametrize("pattern", ["p[unknown()]", "p[$missing]", "q:p"], ids=["function", "variable", "prefix"])
def test_number_matcher_errors(
    attribute: str, pattern: str, matcher_transform: Callable[[str, str, str], Transform]
) -> None:
    transform: Final = matcher_transform(
        "root/p", f'<xsl:number count="p"/><xsl:number level="any" {attribute}="{pattern}"/>', ""
    )
    for source in ("<root><p/></root>", "<root><p/><p/></root>"):
        with pytest.raises(ValueError, match=r"^xslt: xsl:number pattern error$"):
            transform(parse_xml(source))
    assert not transform(parse_xml("<root><q/></root>"))


@pytest.fixture
def matcher_transform() -> Callable[[str, str, str], Transform]:
    def compile_matcher(select: str, instructions: str, declarations: str) -> Transform:
        return Transform(
            parse_xml(f"""<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
                <xsl:output method="text"/>{declarations}<xsl:template match="/">
                <xsl:for-each select="{select}">{instructions}<xsl:text>|</xsl:text></xsl:for-each>
                </xsl:template></xsl:stylesheet>""")
        )

    return compile_matcher
