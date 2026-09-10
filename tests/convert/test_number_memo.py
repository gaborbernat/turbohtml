"""Numbering reuse must respect the current node's counting criteria."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable

_PAIR: Final = "<xsl:number/><xsl:text>:</xsl:text><xsl:number/>"


@pytest.mark.parametrize(
    ("source", "selection", "numbers", "expected"),
    [
        pytest.param("<r><n/><n/><n/></r>", "r/n", _PAIR, "1:1|2:2|3:3|", id="adjacent-siblings"),
        pytest.param("<r><a/><b/><a/><b/></r>", "r/*", _PAIR, "1:1|1:1|2:2|2:2|", id="same-length-names"),
        pytest.param("<r><a/><bb/><a/></r>", "r/*", _PAIR, "1:1|1:1|2:2|", id="different-length-names"),
        pytest.param(
            "<r><a/>x<!--first-->longer<a/><!--second--></r>",
            "r/node()",
            _PAIR,
            "1:1|1:1|1:1|2:2|2:2|2:2|",
            id="mixed-node-types",
        ),
        pytest.param("<r><n/><n/><n/><n/></r>", "r/n[position() mod 2 = 0]", _PAIR, "2:2|4:4|", id="skipped-siblings"),
        pytest.param(
            '<r><n id="1"/><n id="2"/><n id="3"/></r>',
            "r/n",
            '<xsl:sort select="@id" data-type="number" order="descending"/>' + _PAIR,
            "3:3|2:2|1:1|",
            id="reverse-siblings",
        ),
        pytest.param(
            "<r><g><n/><n/></g><g><n/><n/></g></r>",
            "r/g/n",
            _PAIR,
            "1:1|2:2|1:1|2:2|",
            id="different-parents",
        ),
        pytest.param(
            "<r><n><n/><n/></n><n><n/></n></r>",
            "r/n/n",
            '<xsl:number level="multiple" format="1.1"/><xsl:text>:</xsl:text>'
            '<xsl:number level="multiple" from="n[parent::r]" format="1.1"/>',
            "1.1:1|1.2:2|2.1:1|",
            id="multiple-levels-from-boundary",
        ),
        pytest.param(
            "<r><n/><n/></r>",
            "r/n",
            '<xsl:number from="n"/><xsl:text>:</xsl:text><xsl:number/>',
            ":1|:2|",
            id="from-excludes-current-node",
        ),
        pytest.param(
            "<r><a/><b/><a/><b/></r>",
            "r/*",
            '<xsl:number/><xsl:text>:</xsl:text><xsl:number count="a"/><xsl:text>:</xsl:text><xsl:number/>',
            "1:1:1|1::1|2:2:2|2::2|",
            id="explicit-default-interleaving",
        ),
        pytest.param(
            '<r><book cat="A"/><book cat="B"/><book cat="A"/></r>',
            "r/book",
            '<xsl:number count="book[@cat=current()/@cat]"/><xsl:text>:</xsl:text>'
            '<xsl:number count="book[@cat=current()/@cat]"/>',
            "1:1|1:1|2:2|",
            id="explicit-current-dependent-patterns",
        ),
        pytest.param(
            "<r><n/><n/></r>",
            "r/n",
            '<xsl:number/><xsl:text>:</xsl:text><xsl:number value="7"/><xsl:text>:</xsl:text><xsl:number/>',
            "1:7:1|2:7:2|",
            id="explicit-value-interleaving",
        ),
        pytest.param('<r><n id="a"/><n id="b"/></r>', "r/n/@id", _PAIR, "1:1|1:1|", id="attributes"),
    ],
)
def test_number_memo_criteria(
    source: str, selection: str, numbers: str, expected: str, compile_numbers: Callable[[str], Transform]
) -> None:
    compiled: Final = compile_numbers(
        f'<xsl:template match="/"><xsl:for-each select="{selection}">{numbers}'
        "<xsl:text>|</xsl:text></xsl:for-each></xsl:template>"
    )
    assert compiled(parse_xml(source)) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("<r><n/><n/><n/></r>", "1:1|2:2|3:3|", id="same-name"),
        pytest.param("<r><a/><b/><a/></r>", "1:1|1:1|2:2|", id="changing-name"),
    ],
)
def test_number_memo_same_instruction_target(
    source: str, expected: str, compile_numbers: Callable[[str], Transform]
) -> None:
    compiled: Final = compile_numbers(
        '<xsl:template name="number"><xsl:number/></xsl:template>'
        '<xsl:template match="/"><xsl:for-each select="r/*">'
        '<xsl:call-template name="number"/><xsl:text>:</xsl:text><xsl:call-template name="number"/>'
        "<xsl:text>|</xsl:text></xsl:for-each></xsl:template>"
    )
    assert compiled(parse_xml(source)) == expected


def test_number_memo_compiled_transform_reuse(compile_numbers: Callable[[str], Transform]) -> None:
    compiled: Final = compile_numbers(
        f'<xsl:template match="/"><xsl:for-each select="r/*">{_PAIR}'
        "<xsl:text>|</xsl:text></xsl:for-each></xsl:template>"
    )
    documents: Final = [parse_xml(source) for source in ("<r><n/><n/><n/></r>", "<r><n/></r>", "<r><a/><b/><a/></r>")]
    assert [compiled(document) for document in [*documents, documents[0]]] == [
        "1:1|2:2|3:3|",
        "1:1|",
        "1:1|1:1|2:2|",
        "1:1|2:2|3:3|",
    ]


@pytest.fixture
def compile_numbers() -> Callable[[str], Transform]:
    def compile_body(body: str) -> Transform:
        return Transform(
            parse_xml(
                '<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
                f'<xsl:output method="text"/>{body}</xsl:stylesheet>'
            )
        )

    return compile_body
