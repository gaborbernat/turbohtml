from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG, XMLSchema


@pytest.mark.parametrize("kind", [pytest.param("xsd", id="xsd"), pytest.param("rng", id="relax-ng")])
@pytest.mark.parametrize("negated", [pytest.param(False, id="positive"), pytest.param(True, id="negated")])
@pytest.mark.parametrize(
    ("codepoint", "inside"),
    [
        pytest.param(0x400, True, id="first"),
        pytest.param(0x47F, True, id="last"),
        pytest.param(0x480, False, id="outside"),
    ],
)
def test_growing_pattern_class(kind: str, *, negated: bool, codepoint: int, inside: bool) -> None:
    pattern: Final[str] = "[" + ("^" if negated else "") + "".join(chr(index) for index in range(0x400, 0x480)) + "]"
    schema: Final[XMLSchema | RelaxNG]
    if kind == "xsd":
        schema = XMLSchema(
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="value"><xs:simpleType>'
            f'<xs:restriction base="xs:string"><xs:pattern value="{pattern}"/></xs:restriction>'
            "</xs:simpleType></xs:element></xs:schema>"
        )
    else:
        schema = RelaxNG(
            '<element xmlns="http://relaxng.org/ns/structure/1.0" name="value" '
            'datatypeLibrary="http://www.w3.org/2001/XMLSchema-datatypes"><data type="string">'
            f'<param name="pattern">{pattern}</param></data></element>'
        )
    assert schema.validate(parse_xml(f"<value>{chr(codepoint)}</value>")).valid is (inside != negated)
