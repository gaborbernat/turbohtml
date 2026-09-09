from __future__ import annotations

import gc
from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG, XMLSchema

if TYPE_CHECKING:
    from types import ModuleType


@pytest.mark.parametrize(
    ("schema_type", "source"),
    [
        pytest.param(
            XMLSchema,
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="value"><xs:simpleType>'
            '<xs:restriction base="xs:string"><xs:pattern value="[a-z]+"/></xs:restriction>'
            "</xs:simpleType></xs:element></xs:schema>",
            id="xsd-pattern",
        ),
        pytest.param(
            RelaxNG,
            '<element xmlns="http://relaxng.org/ns/structure/1.0" name="value" '
            'datatypeLibrary="http://www.w3.org/2001/XMLSchema-datatypes">'
            '<data type="string"><param name="pattern">[a-z]+</param></data></element>',
            id="rng-pattern",
        ),
        pytest.param(
            RelaxNG,
            '<grammar xmlns="http://relaxng.org/ns/structure/1.0"><start><ref name="root"/></start>'
            '<define name="root"><element name="value"><oneOrMore><element name="item"><text/>'
            "</element></oneOrMore></element></define></grammar>",
            id="rng-definition",
        ),
    ],
)
@pytest.mark.parametrize("valid", [pytest.param(True, id="valid"), pytest.param(False, id="invalid")])
def test_schema_releases_validation_buffers(
    schema_type: type[XMLSchema | RelaxNG], source: str, *, valid: bool
) -> None:
    # PyPy has no tracemalloc; its collector also uses a different reclamation schedule.
    tracing: Final[ModuleType] = pytest.importorskip("tracemalloc")
    schema: Final = schema_type(source)
    document: Final = parse_xml(
        ("<value><item>text</item></value>" if "oneOrMore" in source else "<value>text</value>")
        if valid
        else "<value>123</value>"
    )
    tracing.start()
    try:
        for _ in range(10):
            assert schema.validate(document).valid is valid
        gc.collect()
        before: Final[int] = tracing.get_traced_memory()[0]
        for _ in range(100):
            assert schema.validate(document).valid is valid
        gc.collect()
        assert tracing.get_traced_memory()[0] - before < 32_768
    finally:
        tracing.stop()
