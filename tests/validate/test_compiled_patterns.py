from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG, XMLSchema

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def pattern_schema() -> Callable[[str, str], XMLSchema | RelaxNG]:
    def make(kind: str, facets: str) -> XMLSchema | RelaxNG:
        if kind == "rng":
            return RelaxNG(
                '<element xmlns="http://relaxng.org/ns/structure/1.0" name="value" '
                'datatypeLibrary="http://www.w3.org/2001/XMLSchema-datatypes"><data type="token">'
                f"{facets}</data></element>"
            )
        restriction: Final = f'<xs:restriction base="xs:token">{facets}</xs:restriction>'
        if kind == "inherited":
            return XMLSchema(
                '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
                f'<xs:simpleType name="base">{restriction}</xs:simpleType>'
                '<xs:element name="value"><xs:simpleType><xs:restriction base="base">'
                '<xs:pattern value="abc[0-9]+"/></xs:restriction></xs:simpleType></xs:element></xs:schema>'
            )
        return XMLSchema(
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="value">'
            f"<xs:simpleType>{restriction}</xs:simpleType></xs:element></xs:schema>"
        )

    return make


@pytest.mark.parametrize("kind", ["inline", "inherited", "rng"])
@pytest.mark.parametrize("concurrent", [False, True], ids=["sequential", "concurrent"])
def test_compiled_patterns_reuse(
    pattern_schema: Callable[[str, str], XMLSchema | RelaxNG], kind: str, *, concurrent: bool
) -> None:
    facets: Final = (
        '<param name="pattern">[a-z]+[0-9]+</param><param name="pattern">abc[0-9]+</param>'
        if kind == "rng"
        else '<xs:pattern value="[a-z]+[0-9]+"/><xs:pattern value="abc[0-9]+"/>'
    )
    schema: Final = pattern_schema(kind, facets)
    documents: Final = [parse_xml(f"<value>{value}</value>") for value in (" abc123 ", "abc", "def123", "abc0") * 8]
    if concurrent:
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(schema.validate, documents))
    else:
        results = [schema.validate(document) for document in documents]
    assert [result.valid for result in results] == [True, False, False, True] * 8


@pytest.mark.parametrize(
    ("kind", "pattern", "values", "expected"),
    [
        pytest.param("inline", "", ("", "a", ""), [True, False, True], id="xsd-empty"),
        pytest.param("inline", "(a?)*b", ("aaab", "aaa", "b"), [True, False, True], id="epsilon-revisit"),
        pytest.param("rng", "", ("", "a", ""), [False, False, False], id="rng-empty"),
        pytest.param("inline", "(ab|cd)*", ("abcd", "abc", ""), [True, False, True], id="xsd-epsilon-cycle"),
        pytest.param("rng", "(ab|cd)*", ("abcd", "abc", ""), [True, False, False], id="rng-epsilon-cycle"),
        pytest.param("inline", "é+[0-9]?", ("éé1", "ee1", "é"), [True, False, True], id="xsd-unicode"),
        pytest.param("rng", "é+[0-9]?", ("éé1", "ee1", "é"), [True, False, True], id="rng-unicode"),
    ],
)
def test_compiled_pattern_outputs(
    pattern_schema: Callable[[str, str], XMLSchema | RelaxNG],
    kind: str,
    pattern: str,
    values: tuple[str, str, str],
    expected: list[bool],
) -> None:
    facet: Final = f'<param name="pattern">{pattern}</param>' if kind == "rng" else f'<xs:pattern value="{pattern}"/>'
    schema: Final = pattern_schema(kind, facet)
    assert [schema.validate(parse_xml(f"<value>{value}</value>")).valid for value in values] == expected


def test_compiled_pattern_diagnostic(pattern_schema: Callable[[str, str], XMLSchema | RelaxNG]) -> None:
    schema: Final = pattern_schema("inline", '<xs:pattern value="[a-z]+"/>')
    assert [
        [(error.type, error.message) for error in schema.validate(parse_xml(f"<value>{value}</value>")).errors]
        for value in ("123", "abc", "123")
    ] == [
        [("facet", "value does not match the required pattern")],
        [],
        [("facet", "value does not match the required pattern")],
    ]


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param("<xs:pattern/>", id="missing-value"),
        pytest.param('<pattern xmlns="urn:foreign" value="[0-9]+"/>', id="foreign-namespace"),
    ],
)
def test_compiled_pattern_ignores_inapplicable_facets(
    pattern_schema: Callable[[str, str], XMLSchema | RelaxNG], extra: str
) -> None:
    schema: Final = pattern_schema("inline", extra + '<xs:pattern value="[a-z]+"/>')
    assert [schema.validate(parse_xml(f"<value>{value}</value>")).valid for value in ("abc", "123")] == [True, False]
