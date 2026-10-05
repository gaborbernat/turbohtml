from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG

_NAMESPACE: Final = "http://relaxng.org/ns/structure/1.0"
_XSD: Final = "http://www.w3.org/2001/XMLSchema-datatypes"


@pytest.mark.parametrize("attribute", [pytest.param(False, id="text"), pytest.param(True, id="attribute")])
@pytest.mark.parametrize(
    ("attributes", "literal", "content", "expected"),
    [
        pytest.param(("", ""), "alpha beta", "alpha beta", True, id="exact"),
        pytest.param(("", ""), "alpha beta", " alpha  beta ", True, id="collapse-spaces"),
        pytest.param(("", ""), "alpha beta", "&#x9;alpha&#xA; beta&#xD;", True, id="xml-whitespace"),
        pytest.param(("", ""), " alpha&#x9; beta ", "alpha beta", True, id="schema-whitespace"),
        pytest.param(("", ""), " alpha&#x9; beta ", " alpha  beta ", True, id="both-whitespace"),
        pytest.param(("", f'datatypeLibrary="{_XSD}"'), "alpha beta", " alpha  beta ", True, id="reset-xsd"),
        pytest.param(("", 'datatypeLibrary="urn:unknown"'), "alpha beta", " alpha  beta ", True, id="reset-unknown"),
        pytest.param(("", ""), "alpha beta", "alphabeta", False, id="missing-space"),
        pytest.param(("", ""), "alpha beta", "alpha gamma", False, id="different-token"),
        pytest.param(("", ""), "alpha beta", "alpha&#xA0;beta", False, id="nonbreaking-space"),
        pytest.param(("", ""), "alpha&#xA0;beta", "alpha&#xA0;beta", True, id="literal-nonbreaking-space"),
        pytest.param(('type="string"', ""), "alpha beta", "alpha beta", True, id="string-exact"),
        pytest.param(('type="string"', ""), "alpha beta", " alpha  beta ", False, id="string-spacing"),
        pytest.param(('type="token"', ""), "alpha beta", " alpha  beta ", True, id="explicit-token"),
        pytest.param(
            ('type="token"', f'datatypeLibrary="{_XSD}"'), "alpha beta", " alpha  beta ", True, id="xsd-token"
        ),
    ],
)
def test_relaxng_value_default_token(
    *, attribute: bool, attributes: tuple[str, str], literal: str, content: str, expected: bool
) -> None:
    value: Final = f"<value {attributes[0]}>{literal}</value>"
    pattern: Final = f'<attribute name="content">{value}</attribute>' if attribute else value
    validator: Final = RelaxNG(f'<element xmlns="{_NAMESPACE}" name="doc" {attributes[1]}>{pattern}</element>')
    document: Final = f'<doc content="{content}"/>' if attribute else f"<doc>{content}</doc>"
    assert tuple(validator.validate(parse_xml(document)).valid for _ in range(2)) == (expected, expected)
