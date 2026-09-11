from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import XMLSchema

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def facet_schema() -> Callable[[str], XMLSchema]:
    def make(declarations: str) -> XMLSchema:
        return XMLSchema(f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">{declarations}</xs:schema>')

    return make


@pytest.mark.parametrize("count", [1, 9, 32], ids=["single", "growth", "many-types"])
def test_compiled_facet_type_lookup(facet_schema: Callable[[str], XMLSchema], count: int) -> None:
    types: Final = "".join(
        f'<xs:simpleType name="type{index}"><xs:restriction base="xs:int">'
        f'<xs:minInclusive value="{index}"/><xs:maxInclusive value="{index}"/>'
        "</xs:restriction></xs:simpleType>"
        for index in range(count)
    )
    elements: Final = "".join(f'<xs:element name="value{index}" type="type{index}"/>' for index in range(count))
    schema: Final = facet_schema(
        types
        + '<xs:element name="root"><xs:complexType><xs:sequence>'
        + elements
        + "</xs:sequence></xs:complexType></xs:element>"
    )
    documents: Final = [
        parse_xml(
            "<root>" + "".join(f"<value{index}>{index + offset}</value{index}>" for index in range(count)) + "</root>"
        )
        for offset in (0, 1, 0)
    ]
    assert [schema.validate(document).valid for document in documents] == [True, False, True]


@pytest.mark.parametrize("count", [40, 41, 42], ids=["before-cutoff", "last-builtin", "after-cutoff"])
@pytest.mark.parametrize("location", ["element", "attribute"])
def test_compiled_facet_inheritance_cutoff(facet_schema: Callable[[str], XMLSchema], count: int, location: str) -> None:
    types: Final = "".join(
        f'<xs:simpleType name="type{index}"><xs:restriction base="'
        + (f"type{index + 1}" if index + 1 < count else "xs:int")
        + '"/></xs:simpleType>'
        for index in range(count)
    )
    declaration: Final = (
        '<xs:element name="value" type="type0"/>'
        if location == "element"
        else '<xs:element name="value"><xs:complexType><xs:attribute name="number" type="type0"/>'
        "</xs:complexType></xs:element>"
    )
    schema: Final = facet_schema(types + declaration)
    document: Final = parse_xml("<value>abc</value>" if location == "element" else '<value number="abc"/>')
    assert schema.validate(document).valid is (count == 42)


@pytest.mark.parametrize("concurrent", [False, True], ids=["sequential", "concurrent"])
def test_compiled_facet_enumeration_reuse(facet_schema: Callable[[str], XMLSchema], *, concurrent: bool) -> None:
    schema: Final = facet_schema(
        '<xs:simpleType name="base"><xs:restriction base="xs:token">'
        '<xs:enumeration value="abc"/></xs:restriction></xs:simpleType>'
        '<xs:simpleType name="derived"><xs:restriction base="base">'
        '<xs:enumeration value="def"/><xs:minLength value="3"/></xs:restriction></xs:simpleType>'
        '<xs:element name="value" type="derived"/>'
    )
    documents: Final = [parse_xml(f"<value>{value}</value>") for value in (" abc ", "def", "ghi", "ab") * 8]
    if concurrent:
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(schema.validate, documents))
    else:
        results = [schema.validate(document) for document in documents]
    assert [result.valid for result in results] == [True, True, False, False] * 8


def test_compiled_facet_cyclic_inheritance(facet_schema: Callable[[str], XMLSchema]) -> None:
    schema: Final = facet_schema(
        '<xs:simpleType name="first"><xs:restriction base="second">'
        '<xs:pattern value="[a-z]+"/></xs:restriction></xs:simpleType>'
        '<xs:simpleType name="second"><xs:restriction base="first">'
        '<xs:pattern value="abc"/></xs:restriction></xs:simpleType>'
        '<xs:element name="value" type="first"/>'
    )
    assert [schema.validate(parse_xml(f"<value>{value}</value>")).valid for value in ("abc", "def", "abc1")] == [
        True,
        False,
        False,
    ]


@pytest.mark.parametrize(
    "derivation",
    [
        pytest.param('<xs:list itemType="xs:int"/>', id="list"),
        pytest.param('<xs:union memberTypes="xs:int xs:double"/>', id="union"),
    ],
)
def test_compiled_facet_string_fallback(facet_schema: Callable[[str], XMLSchema], derivation: str) -> None:
    schema: Final = facet_schema(
        '<xs:simpleType name="item"><xs:restriction><xs:simpleType>'
        + derivation
        + '</xs:simpleType><xs:maxLength value="3"/></xs:restriction></xs:simpleType>'
        '<xs:element name="root"><xs:complexType><xs:sequence><xs:element name="value" type="item"/>'
        '</xs:sequence><xs:attribute name="code" type="item"/></xs:complexType></xs:element>'
    )
    assert [
        schema.validate(parse_xml(f'<root code="{value}"><value>{value}</value></root>')).valid
        for value in ("abc", "abcd")
    ] == [True, False]


def test_compiled_facets_with_schema_comments(facet_schema: Callable[[str], XMLSchema]) -> None:
    schema: Final = facet_schema(
        '<!--declaration--><xs:element name="value"><xs:simpleType><!--restriction-->'
        '<xs:restriction base="xs:int"><xs:minInclusive value="3"/>'
        "</xs:restriction></xs:simpleType></xs:element>"
    )
    assert [schema.validate(parse_xml(f"<value>{value}</value>")).valid for value in (3, 2)] == [True, False]
