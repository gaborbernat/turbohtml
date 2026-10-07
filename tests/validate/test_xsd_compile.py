from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import XMLSchema

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

_XS: Final = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
_INVALID: Final[list[ParameterSet]] = [
    pytest.param('<xs:element name="v" type="xs:notAType"/>', "does not resolve", id="unknown-global-type"),
    pytest.param('<xs:element name="v" type="xs:weirdUnknownType"/>', "does not resolve", id="old-string-fallback"),
    pytest.param(
        '<xs:element name="v"><xs:complexType><xs:sequence><xs:element name="child" type="xs:notAType"/>'
        "</xs:sequence></xs:complexType></xs:element>",
        "does not resolve",
        id="unknown-local-type",
    ),
    pytest.param(
        '<xs:element name="v"><xs:complexType><xs:attribute name="key" type="xs:notAType"/>'
        "</xs:complexType></xs:element>",
        "does not resolve",
        id="unknown-attribute-type",
    ),
    pytest.param('<xs:element name="v" type=""/>', "does not resolve", id="empty-type"),
    pytest.param('<xs:element type="xs:string"/>', "requires a name", id="missing-global-name"),
    pytest.param('<xs:element name="" type="xs:string"/>', "requires a name", id="empty-global-name"),
    pytest.param('<xs:element ref="v"/>', "requires a name", id="global-reference"),
    pytest.param(
        '<xs:simpleType name="notAType"><xs:restriction base="xs:string"/></xs:simpleType>'
        '<xs:element name="v" type="xs:notAType"/>',
        "does not resolve",
        id="wrong-namespace-collision",
    ),
]


@pytest.mark.parametrize(("declarations", "message"), _INVALID)
def test_xsd_compile_rejects_unresolved_type_and_nameless_global(declarations: str, message: str) -> None:
    for source in (f"<xs:schema {_XS}>{declarations}</xs:schema>",) * 2:
        with pytest.raises(ValueError, match=message):
            XMLSchema(source)


@pytest.mark.parametrize(
    ("type_name", "value"),
    [
        pytest.param("anyType", "plain", id="anyType"),
        pytest.param("NOTATION", "xs:known", id="notation-name"),
        pytest.param("ID", "known", id="id"),
        pytest.param("IDREF", "known", id="idref"),
        pytest.param("IDREFS", "known other", id="idrefs"),
        pytest.param("ENTITY", "known", id="entity"),
        pytest.param("ENTITIES", "known other", id="entities"),
        pytest.param("NMTOKENS", "known other", id="nmtokens"),
        pytest.param("gYearMonth", "2026-10", id="year-month"),
        pytest.param("gYear", "2026", id="year"),
        pytest.param("gMonthDay", "--10-06", id="month-day"),
        pytest.param("gDay", "---06", id="day"),
        pytest.param("gMonth", "--10", id="month"),
        pytest.param("string", "plain", id="handled-builtin"),
    ],
)
def test_xsd_compile_preserves_known_builtin_names(type_name: str, value: str) -> None:
    validator: Final = XMLSchema(f'<xs:schema {_XS}><xs:element name="v" type="xs:{type_name}"/></xs:schema>')
    assert [validator.is_valid(parse_xml(f"<v>{value}</v>")), validator.is_valid(parse_xml("<other/>"))] == [
        True,
        False,
    ]


@pytest.mark.parametrize(
    ("declarations", "document", "expected"),
    [
        pytest.param(
            "<xs:annotation><xs:documentation>schema</xs:documentation></xs:annotation>"
            '<xs:element name="v" type="xs:string"/>',
            "<v>plain</v>",
            True,
            id="nameless-annotation",
        ),
        pytest.param(
            '<foreign xmlns="urn:annotation"/><xs:element name="v" type="xs:string"/>',
            "<v>plain</v>",
            True,
            id="foreign-annotation",
        ),
        pytest.param(
            '<xs:element name="child" type="xs:int"/><xs:element name="v"><xs:complexType>'
            '<xs:sequence><xs:element ref="child"/></xs:sequence></xs:complexType></xs:element>',
            "<v><child>7</child></v>",
            True,
            id="local-reference",
        ),
        pytest.param(
            '<xs:simpleType name="plain"><xs:restriction base="xs:integer"/></xs:simpleType>'
            '<xs:element name="v" type="plain"/>',
            "<v>bad</v>",
            False,
            id="declared-simple-type",
        ),
        pytest.param(
            '<xs:complexType name="plain"><xs:sequence><xs:element name="child" type="xs:int"/>'
            '</xs:sequence></xs:complexType><xs:element name="v" type="plain"/>',
            "<v><child>7</child></v>",
            True,
            id="declared-complex-type",
        ),
    ],
)
def test_xsd_compile_preserves_declarations(declarations: str, document: str, *, expected: bool) -> None:
    validator: Final = XMLSchema(f"<xs:schema {_XS}>{declarations}</xs:schema>")
    assert [validator.is_valid(parse_xml(document)) for _ in range(2)] == [expected, expected]
