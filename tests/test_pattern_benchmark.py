from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest
from bench.ci import benchmarks
from bench.core import OPERATIONS

from turbohtml import parse_xml
from turbohtml.validate import XMLSchema

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("validate-pattern-reuse", [True, False], id="two-patterns"),
        pytest.param("validate-pattern-plain", [True, True], id="no-patterns"),
    ],
)
def test_pattern_benchmark_output(name: str, expected: list[bool]) -> None:
    _, _, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == name)
    source, document = cast("tuple[str, str]", load())
    schema: Final = XMLSchema(source)
    assert [
        schema.validate(parse_xml(text)).valid for text in (document, document.replace("abc123", "abc"))
    ] == expected


def test_pattern_compile_benchmark_output() -> None:
    _, _, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == "compile-pattern")
    compile_schema: Final = cast("Callable[[str], XMLSchema]", OPERATIONS["compile-pattern"][0])
    schema: Final = compile_schema(cast("str", load()))
    assert [
        schema.validate(parse_xml(f"<root><value>{value}</value></root>")).valid for value in ("abc123", "abc")
    ] == [
        True,
        False,
    ]


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
