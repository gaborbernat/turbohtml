"""Prefix numbering handles reverse visits and changing default node kinds."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("context", "declarations", "instructions", "expected"),
    [
        pytest.param(
            ('<root><p id="1"/><p id="2"/><p id="3"/></root>', "root/*"),
            "",
            '<xsl:sort select="@id" data-type="number" order="descending"/><xsl:number level="any"/>',
            "3|2|1|",
            id="reverse-order",
        ),
        pytest.param(
            ("<root><p/><q/><p/></root>", "root/*"), "", '<xsl:number level="any"/>', "1|1|2|", id="mixed-default-names"
        ),
        pytest.param(
            ("<root><p/><long/><p/></root>", "root/*"),
            "",
            '<xsl:number level="any"/>',
            "1|1|2|",
            id="different-name-lengths",
        ),
        pytest.param(
            ("<root><p/><p/><p/></root>", "root/*"),
            "",
            '<xsl:number level="any" value="7"/>',
            "7|7|7|",
            id="explicit-value",
        ),
        pytest.param(
            ("<root><section><p/><p/></section><section><p/></section></root>", "//p"),
            "",
            '<xsl:number level="any" count="p" from="section"/>',
            "1|2|1|",
            id="pattern-resets",
        ),
        pytest.param(
            ("<root><p/><p/></root>", "root/p"),
            "",
            '<xsl:number level="any"/>' * 8,
            "11111111|22222222|",
            id="eight-instructions-same-node",
        ),
        pytest.param(
            ("<root><section><p/><p/></section><section><p/><p/></section></root>", "root/section/p"),
            "",
            '<xsl:number level="any"/>',
            "1|2|3|4|",
            id="different-parents",
        ),
        pytest.param(
            ("<root><section><p/><p/></section><section><p/><p/></section></root>", "root/section/p"),
            "",
            '<xsl:number level="any"/><xsl:text>/</xsl:text><xsl:number/>'
            '<xsl:text>/</xsl:text><xsl:number level="any"/>',
            "1/1/1|2/2/2|3/1/3|4/2/4|",
            id="sibling-interleaving",
        ),
        pytest.param(
            ("<root><section><p/><p/></section><section><p/><p/></section></root>", "root/section/p"),
            "",
            '<xsl:number level="any"/><xsl:text>/</xsl:text>'
            '<xsl:number level="any" count="p" from="section"/><xsl:text>/</xsl:text>'
            '<xsl:number level="any" value="7"/><xsl:text>/</xsl:text><xsl:number level="any"/>',
            "1/1/7/1|2/2/7/2|3/1/7/3|4/2/7/4|",
            id="explicit-options-interleaving",
        ),
        pytest.param(
            ("<root><section><p/><p/></section><section><p/><p/></section></root>", "root/section/p"),
            "",
            '<xsl:number level="any" count="section"/>',
            "1|1|2|2|",
            id="explicit-count-only",
        ),
        pytest.param(
            ("<root><section><p/><p/></section><section><p/><p/></section></root>", "root/section/p"),
            "",
            '<xsl:number level="any" from="section"/>',
            "1|2|1|2|",
            id="explicit-from-only",
        ),
        pytest.param(
            ("<root>one<!--a--><?go a?><p/>two<!--b--><?go b?><q/><p/></root>", "root/node()"),
            "",
            '<xsl:number level="any"/>',
            "1|1|1|1|2|2|2|1|2|",
            id="changing-node-types-and-names",
        ),
        *(
            pytest.param(
                ("<root>one<!--a--><?go a?><p/>two<!--b--><?go b?></root>", f"root/{kind}()"),
                "",
                '<xsl:number level="any"/>',
                "1|2|",
                id=f"repeated-{kind}",
            )
            for kind in ("text", "comment", "processing-instruction")
        ),
        pytest.param(
            ("<root>  <p>A</p> \n <p>B</p> </root>", "root/p/text()"),
            '<xsl:strip-space elements="*"/>',
            '<xsl:number level="any"/>',
            "1|2|",
            id="stripped-whitespace",
        ),
        pytest.param(
            ("<root>  <p>A</p> \n <p>B</p> </root>", "root/p/text()"),
            "",
            '<xsl:number level="any"/>',
            "2|4|",
            id="preserved-whitespace",
        ),
        pytest.param(
            ('<root><p name="a"/><p name="b"/></root>', "root/p/@name"),
            "",
            '<xsl:number level="any"/>',
            "1|1|",
            id="attribute-context",
        ),
    ],
)
def test_number_any_criteria(
    context: tuple[str, str],
    declarations: str,
    instructions: str,
    expected: str,
    prefix_transform: Callable[[str, str], Transform],
) -> None:
    transform: Final = prefix_transform(
        f'<xsl:for-each select="{context[1]}">{instructions}<xsl:text>|</xsl:text></xsl:for-each>', declarations
    )
    document: Final = parse_xml(context[0])
    assert [transform(document) for _ in range(2)] == [expected, expected]


@pytest.mark.parametrize(
    ("visits", "expected"),
    [
        pytest.param((1, 3, 2, 4, 1), "1|3|2|4|1|", id="cached-reverse-then-forward"),
        pytest.param((4, 2, 3, 1, 4), "4|2|3|1|4|", id="first-reverse-then-forward"),
        pytest.param((1, 1, 1, 3, 2, 4), "1|1|1|3|2|4|", id="same-node-before-index"),
    ],
)
def test_number_any_visit_order(
    visits: tuple[int, ...], expected: str, prefix_transform: Callable[[str, str], Transform]
) -> None:
    transform: Final = prefix_transform(
        "".join(
            f'<xsl:for-each select="root/p[{index}]"><xsl:number level="any"/><xsl:text>|</xsl:text></xsl:for-each>'
            for index in visits
        ),
        "",
    )
    assert transform(parse_xml("<root><p/><p/><p/><p/></root>")) == expected


@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
def test_number_any_compiled_reuse_across_documents(
    prefix_transform: Callable[[str, str], Transform], *, reverse: bool
) -> None:
    transform: Final = prefix_transform(
        '<xsl:for-each select="root/p">'
        + ('<xsl:sort select="@id" data-type="number" order="descending"/>' if reverse else "")
        + '<xsl:number level="any"/><xsl:text>|</xsl:text></xsl:for-each>',
        "",
    )
    assert [
        transform(parse_xml(source))
        for source in (
            '<root><p id="1"/><p id="2"/><p id="3"/></root>',
            '<root><p id="1"/></root>',
            '<root><p id="1"/><p id="2"/></root>',
        )
    ] == (["3|2|1|", "1|", "2|1|"] if reverse else ["1|2|3|", "1|", "1|2|"])


@pytest.fixture
def prefix_transform() -> Callable[[str, str], Transform]:
    def compile_prefix(body: str, declarations: str) -> Transform:
        return Transform(
            parse_xml(
                '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
                f'<xsl:output method="text"/>{declarations}<xsl:template match="/">{body}</xsl:template>'
                "</xsl:stylesheet>"
            )
        )

    return compile_prefix
