from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG

_NAMESPACE: Final = "http://relaxng.org/ns/structure/1.0"
_XSD: Final = "http://www.w3.org/2001/XMLSchema-datatypes"


@pytest.mark.parametrize("attribute", [pytest.param(False, id="text"), pytest.param(True, id="attribute")])
@pytest.mark.parametrize(
    ("pattern", "content", "expected"),
    [
        pytest.param(
            '<data type="token"><except><value type="token">x</value></except></data>', "x", False, id="single-excluded"
        ),
        pytest.param(
            '<data type="token"><except><value type="token">x</value></except></data>', "y", True, id="single-allowed"
        ),
        pytest.param(
            '<data type="token"><except><value type="token">x</value>'
            '<value type="token">y</value><value type="token">z</value></except></data>',
            "x",
            False,
            id="multiple-first",
        ),
        pytest.param(
            '<data type="token"><except><value type="token">x</value>'
            '<value type="token">y</value><value type="token">z</value></except></data>',
            "y",
            False,
            id="multiple-middle",
        ),
        pytest.param(
            '<data type="token"><except><value type="token">x</value>'
            '<value type="token">y</value><value type="token">z</value></except></data>',
            "z",
            False,
            id="multiple-last",
        ),
        pytest.param(
            '<data type="token"><except><value type="token">x</value>'
            '<value type="token">y</value><value type="token">z</value></except></data>',
            "xyz",
            True,
            id="multiple-allowed",
        ),
        pytest.param(
            '<data type="token"><except><choice><value type="token">x</value>'
            '<value type="token">y</value></choice></except></data>',
            "y",
            False,
            id="choice-excluded",
        ),
        pytest.param(
            '<data type="token"><except><choice><value type="token">x</value>'
            '<value type="token">y</value></choice></except></data>',
            "z",
            True,
            id="choice-allowed",
        ),
        pytest.param(
            '<data type="token"><except><value type="token">alpha beta</value></except></data>',
            " alpha  beta ",
            False,
            id="token-spacing",
        ),
        pytest.param(
            '<data type="token"><except><value type="string">alpha beta</value></except></data>',
            " alpha  beta ",
            True,
            id="string-spacing",
        ),
        pytest.param(
            '<data type="string"><except><value type="string">alpha beta</value></except></data>',
            "alpha beta",
            False,
            id="string-excluded",
        ),
        pytest.param(
            f'<data datatypeLibrary="{_XSD}" type="integer"><except><value type="integer">7</value></except></data>',
            "not-a-number",
            False,
            id="datatype-invalid",
        ),
        pytest.param(
            f'<data datatypeLibrary="{_XSD}" type="integer"><except><value type="integer">7</value></except></data>',
            "24",
            True,
            id="datatype-allowed",
        ),
        pytest.param(
            f'<data datatypeLibrary="{_XSD}" type="integer"><except><value type="integer">7</value></except></data>',
            "7",
            False,
            id="datatype-excluded",
        ),
        pytest.param(
            f'<data datatypeLibrary="{_XSD}" type="string"><param name="minLength">3</param>'
            '<except><value type="string">abc</value></except></data>',
            "xy",
            False,
            id="facet-invalid",
        ),
        pytest.param(
            f'<data datatypeLibrary="{_XSD}" type="string"><param name="minLength">3</param>'
            '<except><value type="string">abc</value></except></data>',
            "abcd",
            True,
            id="facet-allowed",
        ),
        pytest.param(
            f'<data datatypeLibrary="{_XSD}" type="string"><param name="minLength">3</param>'
            '<except><value type="string">abc</value></except></data>',
            "abc",
            False,
            id="facet-excluded",
        ),
        pytest.param(
            f'<data type="token"><except><data datatypeLibrary="{_XSD}" type="integer"/></except></data>',
            "7",
            False,
            id="excluded-datatype",
        ),
        pytest.param(
            f'<data type="token"><except><data datatypeLibrary="{_XSD}" type="integer"/></except></data>',
            "word",
            True,
            id="excluded-datatype-miss",
        ),
        pytest.param(
            '<data type="token"><except><data type="token"><except><value type="token">x</value>'
            "</except></data></except></data>",
            "x",
            True,
            id="nested-allowed",
        ),
        pytest.param(
            '<data type="token"><except><data type="token"><except><value type="token">x</value>'
            "</except></data></except></data>",
            "y",
            False,
            id="nested-excluded",
        ),
        pytest.param('<data type="token"/>', "x", True, id="without-exclusion"),
        pytest.param(
            '<data type="token"><except>\n<!--annotation--><value type="token">x</value>\n</except></data>',
            "x",
            False,
            id="comments",
        ),
        pytest.param(
            '<data type="token"><except><note xmlns="urn:annotation"/><value type="token">x</value></except></data>',
            "x",
            False,
            id="foreign-annotation",
        ),
    ],
)
def test_relaxng_data_except(*, attribute: bool, pattern: str, content: str, expected: bool) -> None:
    body: Final = f'<attribute name="content">{pattern}</attribute>' if attribute else pattern
    validator: Final = RelaxNG(f'<element xmlns="{_NAMESPACE}" name="doc">{body}</element>')
    document: Final = f'<doc content="{content}"/>' if attribute else f"<doc>{content}</doc>"
    assert tuple(validator.validate(parse_xml(document)).valid for _ in range(2)) == (expected, expected)
