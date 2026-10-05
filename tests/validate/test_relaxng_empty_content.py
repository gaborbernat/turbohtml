from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG

_NAMESPACE: Final = "http://relaxng.org/ns/structure/1.0"


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("", id="absent"),
        pytest.param("<!--comment-->", id="comment"),
        pytest.param("<?probe value?>", id="processing-instruction"),
    ],
)
@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        pytest.param('<data type="string"/>', True, id="data-string"),
        pytest.param('<data type="token"/>', True, id="data-token"),
        pytest.param('<value type="string"></value>', True, id="value-string"),
        pytest.param('<value type="token"></value>', True, id="value-token"),
        pytest.param('<value type="string">x</value>', False, id="nonempty-value"),
        pytest.param(
            '<data datatypeLibrary="http://www.w3.org/2001/XMLSchema-datatypes" type="integer"/>',
            False,
            id="integer",
        ),
        pytest.param("<empty/>", True, id="empty-pattern"),
        pytest.param('<element name="child"><empty/></element>', False, id="required-child"),
        pytest.param('<optional><element name="child"><empty/></element></optional>', True, id="optional-child"),
        pytest.param('<list><zeroOrMore><data type="token"/></zeroOrMore></list>', True, id="empty-list"),
        pytest.param(
            '<attribute name="required"><text/></attribute><data type="string"/>', False, id="required-attribute"
        ),
        pytest.param(
            '<optional><attribute name="optional"><text/></attribute></optional><data type="string"/>',
            True,
            id="optional-attribute",
        ),
    ],
)
def test_rng_empty_content(pattern: str, content: str, *, expected: bool) -> None:
    validator: Final = RelaxNG(f'<element xmlns="{_NAMESPACE}" name="doc">{pattern}</element>')
    assert tuple(validator.validate(parse_xml(f"<doc>{content}</doc>")).valid for _ in range(2)) == (expected, expected)


@pytest.mark.parametrize(
    ("pattern", "content", "expected"),
    [
        pytest.param('<value type="string"></value>', " ", False, id="string-whitespace"),
        pytest.param('<value type="token"></value>', " ", True, id="token-whitespace"),
        pytest.param('<data type="string"/>', "text", True, id="string-text"),
        pytest.param('<data type="token"/>', "<child/>", False, id="data-child"),
        pytest.param('<element name="child"><empty/></element>', "<child/>", True, id="required-child"),
        pytest.param("<empty/>", "text", False, id="empty-text"),
    ],
)
def test_rng_empty_content_controls(pattern: str, content: str, *, expected: bool) -> None:
    validator: Final = RelaxNG(f'<element xmlns="{_NAMESPACE}" name="doc">{pattern}</element>')
    assert tuple(validator.validate(parse_xml(f"<doc>{content}</doc>")).valid for _ in range(2)) == (expected, expected)
