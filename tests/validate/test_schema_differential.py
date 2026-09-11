"""turbohtml's XSD / RELAX NG verdicts cross-checked against lxml.

lxml is a bench dependency, not a test one, and ships no wheels for 3.15, the free-threaded builds, or Windows, so this
module importorskips itself where the oracle is absent and is omitted from the coverage gate (see ``[tool.coverage]``).
It still runs and validates wherever lxml installs, agreeing on the valid/invalid verdict for every case below.
"""

from __future__ import annotations

from typing import Any, Final, cast

import pytest
from bench.ci import benchmarks
from bench.operations import INPUTS

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG, XMLSchema

XS = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
RN = "http://relaxng.org/ns/structure/1.0"

_XSD_CASES = [
    pytest.param(f'<xs:schema {XS}><xs:element name="n" type="xs:int"/></xs:schema>', "<n>42</n>", id="int-valid"),
    pytest.param(f'<xs:schema {XS}><xs:element name="n" type="xs:int"/></xs:schema>', "<n>x</n>", id="int-invalid"),
    pytest.param(
        f'<xs:schema {XS}><xs:element name="d" type="xs:date"/></xs:schema>', "<d>2020-06-15</d>", id="date-valid"
    ),
    pytest.param(
        f'<xs:schema {XS}><xs:element name="d" type="xs:date"/></xs:schema>', "<d>2020-13-40</d>", id="date-invalid"
    ),
    pytest.param(
        f'<xs:schema {XS}><xs:element name="r"><xs:complexType><xs:sequence>'
        '<xs:element name="a" type="xs:string"/><xs:element name="b" type="xs:int" minOccurs="0"/>'
        "</xs:sequence></xs:complexType></xs:element></xs:schema>",
        "<r><a>x</a><b>3</b></r>",
        id="sequence-valid",
    ),
    pytest.param(
        f'<xs:schema {XS}><xs:element name="r"><xs:complexType><xs:sequence>'
        '<xs:element name="a" type="xs:string"/></xs:sequence></xs:complexType></xs:element></xs:schema>',
        "<r><a>x</a><extra/></r>",
        id="sequence-extra-invalid",
    ),
    pytest.param(
        f'<xs:schema {XS}><xs:element name="r"><xs:complexType>'
        '<xs:attribute name="id" type="xs:int" use="required"/></xs:complexType></xs:element></xs:schema>',
        "<r/>",
        id="missing-attr-invalid",
    ),
    pytest.param(
        f'<xs:schema {XS}><xs:element name="v"><xs:simpleType>'
        '<xs:restriction base="xs:string"><xs:enumeration value="a"/><xs:enumeration value="b"/>'
        "</xs:restriction></xs:simpleType></xs:element></xs:schema>",
        "<v>c</v>",
        id="enum-invalid",
    ),
    pytest.param(
        f'<xs:schema {XS}><xs:element name="v"><xs:simpleType>'
        '<xs:restriction base="xs:int"><xs:minInclusive value="0"/><xs:maxInclusive value="10"/>'
        "</xs:restriction></xs:simpleType></xs:element></xs:schema>",
        "<v>11</v>",
        id="range-invalid",
    ),
    pytest.param(
        f'<xs:schema {XS} targetNamespace="urn:x" xmlns="urn:x" elementFormDefault="qualified">'
        '<xs:element name="r"><xs:complexType><xs:sequence>'
        '<xs:element name="a" type="xs:string"/></xs:sequence></xs:complexType></xs:element></xs:schema>',
        '<r xmlns="urn:x"><a>x</a></r>',
        id="namespace-valid",
    ),
]

_RNG_CASES = [
    pytest.param(f'<element name="a" xmlns="{RN}"><text/></element>', "<a>hi</a>", id="text-valid"),
    pytest.param(
        f'<element name="a" xmlns="{RN}"><element name="b"><text/></element></element>',
        "<a><c>x</c></a>",
        id="wrong-child-invalid",
    ),
    pytest.param(
        f'<element name="p" xmlns="{RN}"><interleave>'
        '<element name="a"><text/></element><element name="b"><text/></element></interleave></element>',
        "<p><b>2</b><a>1</a></p>",
        id="interleave-any-order-valid",
    ),
    pytest.param(
        f'<element name="p" xmlns="{RN}"><interleave>'
        '<element name="a"><text/></element><element name="b"><text/></element></interleave></element>',
        "<p><a>1</a></p>",
        id="interleave-missing-invalid",
    ),
    pytest.param(
        f'<element name="r" xmlns="{RN}"><oneOrMore><element name="i"><text/></element></oneOrMore></element>',
        "<r><i>1</i><i>2</i></r>",
        id="oneOrMore-valid",
    ),
    pytest.param(
        f'<element name="r" xmlns="{RN}"><oneOrMore><element name="i"><text/></element></oneOrMore></element>',
        "<r/>",
        id="oneOrMore-empty-invalid",
    ),
    pytest.param(
        f'<element name="e" xmlns="{RN}" datatypeLibrary="http://www.w3.org/2001/XMLSchema-datatypes">'
        '<data type="int"/></element>',
        "<e>7</e>",
        id="data-int-valid",
    ),
    pytest.param(
        f'<element name="e" xmlns="{RN}" datatypeLibrary="http://www.w3.org/2001/XMLSchema-datatypes">'
        '<data type="int"/></element>',
        "<e>seven</e>",
        id="data-int-invalid",
    ),
    pytest.param(
        f'<element name="r" xmlns="{RN}"><attribute name="id"><text/></attribute><text/></element>',
        '<r id="1">x</r>',
        id="attribute-valid",
    ),
    pytest.param(
        f'<element name="r" xmlns="{RN}"><attribute name="id"><text/></attribute><text/></element>',
        "<r>x</r>",
        id="attribute-missing-invalid",
    ),
]


def _lxml_xsd_valid(etree: Any, schema: str, doc: str) -> bool:  # ruff:ignore[any-type]  # lxml.etree is an untyped third-party module
    validator = etree.XMLSchema(etree.fromstring(schema.encode()))
    return bool(validator.validate(etree.fromstring(doc.encode())))


def _lxml_rng_valid(etree: Any, schema: str, doc: str) -> bool:  # ruff:ignore[any-type]  # lxml.etree is an untyped third-party module
    validator = etree.RelaxNG(etree.fromstring(schema.encode()))
    return bool(validator.validate(etree.fromstring(doc.encode())))


@pytest.mark.parametrize(("schema", "doc"), _XSD_CASES)
def test_xsd_matches_lxml(schema: str, doc: str) -> None:
    etree: Any = pytest.importorskip("lxml.etree")
    assert XMLSchema(schema).validate(parse_xml(doc)).valid == _lxml_xsd_valid(etree, schema, doc)


@pytest.mark.parametrize(("schema", "doc"), _RNG_CASES)
def test_relaxng_matches_lxml(schema: str, doc: str) -> None:
    etree: Any = pytest.importorskip("lxml.etree")
    assert RelaxNG(schema).validate(parse_xml(doc)).valid == _lxml_rng_valid(etree, schema, doc)


@pytest.mark.parametrize(
    ("operation", "index", "expected"),
    [
        pytest.param("validate-facets", 0, [True, False], id="derived-type"),
        pytest.param("validate-facets", 1, [True, True], id="builtin-type"),
        pytest.param("compile-facets", 0, [True, False], id="compile"),
    ],
)
def test_lxml_facet_benchmark_output(operation: str, index: int, expected: list[bool]) -> None:
    module: Final = pytest.importorskip("bench.competitors.lxml", exc_type=ImportError)
    etree: Final = pytest.importorskip("lxml.etree", exc_type=ImportError)
    if operation == "compile-facets":
        source = cast("str", INPUTS[operation]()[index][1])
        document = "<root><value>abc123</value></root>"
    else:
        source, document = cast("tuple[str, str]", INPUTS[operation]()[index][1])
    schema: Final = module.OPERATIONS["compile-facets"][0](source)
    assert [
        schema.validate(etree.fromstring(text.encode())) for text in (document, document.replace("abc123", "ab"))
    ] == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("validate-pattern-reuse", [True, False], id="two-patterns"),
        pytest.param("validate-pattern-plain", [True, True], id="no-patterns"),
        pytest.param("compile-pattern", [True, False], id="compile"),
    ],
)
def test_lxml_pattern_benchmark_output(name: str, expected: list[bool]) -> None:
    module: Final = pytest.importorskip("bench.competitors.lxml", exc_type=ImportError)
    etree: Final = pytest.importorskip("lxml.etree", exc_type=ImportError)
    _, _, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == name)
    if name == "compile-pattern":
        source = cast("str", load())
        document = "<root><value>abc123</value></root>"
    else:
        source, document = cast("tuple[str, str]", load())
    schema: Final = module.OPERATIONS["compile-pattern"][0](source)
    assert [
        schema.validate(etree.fromstring(text.encode())) for text in (document, document.replace("abc123", "abc"))
    ] == expected


@pytest.mark.parametrize("index", range(2), ids=["wide-attributes", "small-attributes"])
def test_lxml_attribute_benchmark_output(index: int) -> None:
    etree: Final = pytest.importorskip("lxml.etree", exc_type=ImportError)
    source, document = cast("tuple[str, str]", INPUTS["validate-attributes"]()[index][1])
    schema: Final = etree.XMLSchema(etree.fromstring(source.encode()))
    assert [
        schema.validate(etree.fromstring(text.encode()))
        for text in (document, document.replace("<root ", '<root unknown="x" '))
    ] == [True, False]
