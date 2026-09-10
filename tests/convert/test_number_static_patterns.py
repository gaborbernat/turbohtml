"""Static predicates and unions retain numbering and runtime error behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("context", "patterns", "expected"),
    [
        pytest.param(
            ('<root><p cat="a"/><p cat="b"/><p cat="a"/></root>', "root/p"),
            "count=\"p[@cat='a']\"",
            "1|1|2|",
            id="static-attribute",
        ),
        pytest.param(
            ("<root><section><p/><p/></section><section><p/><p/></section></root>", "//p"),
            'count="p[1]"',
            "1|1|2|2|",
            id="first-child-per-parent",
        ),
        pytest.param(
            ("<root><section><p/><p/></section><section><p/><p/></section></root>", "//p"),
            'count="p[position()=last()]"',
            "0|1|1|2|",
            id="last-child-per-parent",
        ),
        pytest.param(
            ("<root><p/><p/><p/></root>", "root/p"),
            'count="p[position() mod 2 = 1]"',
            "1|1|2|",
            id="positional-arithmetic",
        ),
        pytest.param(
            ("<root><p/><p/><p/></root>", "root/p"),
            'count="p[true()]"',
            "1|2|3|",
            id="builtin-true",
        ),
        pytest.param(
            ('<root><p cat="a"/><p cat="b"/><p cat="a"/></root>', "root/p"),
            "count=\"p[not(@cat='b')]\"",
            "1|1|2|",
            id="builtin-not",
        ),
        pytest.param(
            ("<root><p>A</p><p> bb </p><p/></root>", "root/p"),
            'count="p[string-length(normalize-space(.)) &gt; 1]"',
            "0|1|1|",
            id="nested-builtins",
        ),
        pytest.param(
            ('<root><p cat="a"/><p cat="b"/><p cat="a"/></root>', "root/p"),
            "count=\"p|p[@cat='a']\"",
            "1|2|3|",
            id="overlapping-union",
        ),
        pytest.param(
            ('<root><p cat="a"/><p id="b"/><p/></root>', "root/p"),
            'count="p[count(@cat|@id) &gt; 0]"',
            "1|2|2|",
            id="union-inside-predicate",
        ),
        *(
            pytest.param(
                ('<root><p cat="a"/><p cat="b"/><p cat="a"/></root>', "root/p"),
                f'count="{pattern}"',
                "1|2|2|",
                id=f"dynamic-union-{index}",
            )
            for index, pattern in enumerate((
                "p[@cat='a']|p[@cat=current()/@cat]",
                "p[@cat=current()/@cat]|p[@cat='a']",
            ))
        ),
        pytest.param(
            ("<root><p/><p/></root>", "root/p"),
            'count="q|p[false()]"',
            "0|0|",
            id="empty-static-union",
        ),
        pytest.param(
            (
                (
                    '<root><section cut="yes"><p/><p/></section><section><p/></section>'
                    '<section cut="yes"><p/></section></root>'
                ),
                "//p",
            ),
            'count="p" from="section[@cut=\'yes\']"',
            "1|2|3|1|",
            id="static-from-predicate",
        ),
        pytest.param(
            ("<root>a<p>b</p>c<p>d</p></root>", "//text()"),
            'count="text()"',
            "1|2|3|4|",
            id="text-node-test",
        ),
        pytest.param(
            ('<root><p cat="a"/><p cat="b"/><p cat="a"/></root>', "root/p"),
            "count=\"p[matches(@cat, '^a$')]\"",
            "1|1|2|",
            id="regex-builtin",
        ),
    ],
)
def test_number_static_patterns(
    context: tuple[str, str],
    patterns: str,
    expected: str,
    static_pattern_transform: Callable[[str, str, str], Transform],
) -> None:
    transform: Final = static_pattern_transform(context[1], patterns, "")
    assert [transform(parse_xml(context[0])) for _ in range(2)] == [expected, expected]


@pytest.mark.parametrize(
    ("patterns", "declarations"),
    [
        pytest.param('count="p[true(1)]"', "", id="builtin-arity"),
        pytest.param('count="p[count(1)]"', "", id="builtin-argument-type"),
        pytest.param('count="p[unknown()]"', "", id="unknown-function"),
        pytest.param('count="p|unknown:p"', "", id="unknown-namespace-union"),
        pytest.param('count="p[unknown:value]"', "", id="unknown-namespace-predicate"),
        pytest.param('count="p[$flag]"', '<xsl:variable name="flag" select="true()"/>', id="local-variable"),
        pytest.param('count="p" from="section[true(1)]"', "", id="from-builtin-error"),
    ],
)
def test_number_pattern_failure_reuse(
    patterns: str, declarations: str, static_pattern_transform: Callable[[str, str, str], Transform]
) -> None:
    transform: Final = static_pattern_transform("//p", patterns, declarations)
    for source in ("<root><section><p/></section></root>", "<root><section><p/><p/></section></root>"):
        with pytest.raises(ValueError, match=r"^xslt: xsl:number pattern error$"):
            transform(parse_xml(source))
    assert not transform(parse_xml("<root><q/></root>"))


@pytest.fixture
def static_pattern_transform() -> Callable[[str, str, str], Transform]:
    def compile_patterns(select: str, patterns: str, declarations: str) -> Transform:
        return Transform(
            parse_xml(
                '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
                '<xsl:output method="text"/><xsl:template match="/">'
                f'<xsl:for-each select="{select}">{declarations}'
                f'<xsl:number level="any" {patterns}/><xsl:text>|</xsl:text>'
                "</xsl:for-each></xsl:template></xsl:stylesheet>"
            )
        )

    return compile_patterns
