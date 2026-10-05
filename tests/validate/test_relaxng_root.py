from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG

_NAMESPACE: Final = "http://relaxng.org/ns/structure/1.0"


@pytest.mark.parametrize(
    "schema",
    [
        pytest.param("<thisIsJunk/>", id="jing001"),
        pytest.param('<element name="doc"><empty/></element>', id="absent-namespace"),
        pytest.param('<element xmlns="" name="doc"><empty/></element>', id="empty-default-namespace"),
        pytest.param('<element xmlns="urn:other" name="doc"><empty/></element>', id="foreign-default-namespace"),
        pytest.param(
            '<r:element xmlns:r="urn:other" name="doc"><r:empty/></r:element>', id="foreign-prefixed-namespace"
        ),
        pytest.param(f'<element xmlns:r="{_NAMESPACE}" name="doc"><empty/></element>', id="unused-structure-prefix"),
        pytest.param('<grammar xmlns="urn:other"><start/></grammar>', id="foreign-grammar"),
        pytest.param('<xml:element name="doc"/>', id="reserved-xml-prefix"),
    ],
)
def test_relaxng_rejects_foreign_root(schema: str) -> None:
    for _ in range(2):
        with pytest.raises(ValueError, match="RELAX NG schema root must use the structure namespace"):
            RelaxNG(schema)


@pytest.mark.parametrize(
    "schema",
    [
        pytest.param(f'<element xmlns="{_NAMESPACE}" name="doc"><empty/></element>', id="default-element"),
        pytest.param(f'<r:element xmlns:r="{_NAMESPACE}" name="doc"><r:empty/></r:element>', id="prefixed-element"),
        pytest.param(
            f'<grammar xmlns="{_NAMESPACE}"><start><element name="doc"><empty/></element></start></grammar>',
            id="default-grammar",
        ),
        pytest.param(
            f'<r:grammar xmlns:r="{_NAMESPACE}"><r:start>'
            '<r:element name="doc"><r:empty/></r:element></r:start></r:grammar>',
            id="prefixed-grammar",
        ),
    ],
)
def test_relaxng_structure_root_preserves_validation(schema: str) -> None:
    validator: Final = RelaxNG(schema)
    assert [
        (validator.validate(parse_xml("<doc/>")).valid, validator.validate(parse_xml("<other/>")).valid)
        for _ in range(2)
    ] == [(True, False), (True, False)]
