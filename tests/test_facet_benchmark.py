from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest
from bench.core import OPERATIONS
from bench.operations import INPUTS

from turbohtml import parse_xml
from turbohtml.validate import XMLSchema

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        pytest.param(0, [True, False, False], id="derived-type"),
        pytest.param(1, [True, True, False], id="builtin-type"),
    ],
)
def test_facet_benchmark_output(index: int, expected: list[bool]) -> None:
    source, document = cast("tuple[str, str]", INPUTS["validate-facets"]()[index][1])
    schema: Final = XMLSchema(source)
    assert [
        schema.validate(parse_xml(text)).valid
        for text in (document, document.replace("abc123", "ab"), "<root><other/></root>")
    ] == expected


def test_facet_compile_benchmark_output() -> None:
    compile_schema: Final = cast("Callable[[str], XMLSchema]", OPERATIONS["compile-facets"][0])
    schema: Final = compile_schema(cast("str", INPUTS["compile-facets"]()[0][1]))
    assert [schema.validate(parse_xml(f"<root><value>{value}</value></root>")).valid for value in ("abc123", "ab")] == [
        True,
        False,
    ]
