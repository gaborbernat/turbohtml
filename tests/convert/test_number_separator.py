from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("picture", "single", "multiple"),
    [
        pytest.param(None, "1", "1.2.3", id="default"),
        pytest.param("1", "1", "1.2.3", id="one-token"),
        pytest.param("", "1", "1.2.3", id="empty"),
        pytest.param("()", "()1", "()1.2.3", id="no-token"),
        pytest.param("(1)", "(1)", "(1.2.3)", id="prefix-suffix"),
        pytest.param("(1", "(1", "(1.2.3", id="prefix"),
        pytest.param("1)", "1)", "1.2.3)", id="suffix"),
        pytest.param("(01)", "(01)", "(01.02.03)", id="padded"),
        pytest.param("A", "A", "A.B.C", id="alphabetic"),
        pytest.param("1.1", "1", "1.2.3", id="explicit-period"),
        pytest.param("(A-1)", "(A)", "(A-2-3)", id="explicit-hyphen"),
        pytest.param("1:1/1", "1", "1:2/3", id="two-separators"),
    ],
)
def test_number_separator(
    picture: str | None,
    single: str,
    multiple: str,
    number_transform: Callable[[str | None], Transform],
) -> None:
    transform: Final = number_transform(picture)
    assert [
        transform(parse_xml(source))
        for source in (
            "<root><p><target/></p></root>",
            "<root><p><p/><p><p/><p/><p><target/></p></p></p></root>",
        )
    ] == [single, multiple]


@pytest.fixture
def number_transform() -> Callable[[str | None], Transform]:
    def compile_number(picture: str | None) -> Transform:
        formatting: Final = "" if picture is None else f' format="{picture}"'
        return Transform(
            parse_xml(
                '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
                '<xsl:output method="text"/><xsl:template match="/">'
                '<xsl:for-each select="//target">'
                f'<xsl:number level="multiple" count="p"{formatting}/>'
                "</xsl:for-each></xsl:template></xsl:stylesheet>"
            )
        )

    return compile_number
