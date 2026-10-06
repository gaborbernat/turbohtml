from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from types import ModuleType


@pytest.fixture
def engine() -> ModuleType:
    return pytest.importorskip("fuzz.xsd_inline", exc_type=ImportError)


@pytest.mark.oracle
@pytest.mark.parametrize("seed", range(8))
def test_xsd_inline_generated_labels(engine: ModuleType, seed: int) -> None:
    case: Final = engine.generate(seed)
    assert [(row.engine, row.phase, row.expected, row.actual) for row in engine.compare(case)] == [
        ("turbohtml", "compilation", case.compiles, case.compiles),
        ("libxml2", "compilation", case.compiles, case.compiles),
        *[
            (name, "validation", expected, expected)
            for _, expected in case.documents
            for name in ("turbohtml", "libxml2")
        ],
    ]


@pytest.mark.oracle
@pytest.mark.parametrize("schema", ["<", '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'])
def test_xsd_inline_compile_verdicts(engine: ModuleType, schema: str) -> None:
    expected: Final = schema != "<"
    case: Final = engine.Case(0, schema, expected, ())
    assert [(row.engine, row.phase, row.expected, row.actual) for row in engine.compare(case)] == [
        ("turbohtml", "compilation", expected, expected),
        ("libxml2", "compilation", expected, expected),
    ]


@pytest.mark.oracle
def test_xsd_inline_unavailable_documents_remain_findings(engine: ModuleType) -> None:
    case: Final = engine.Case(0, "<", compiles=False, documents=(("<v/>", True),))
    assert [(row.engine, row.phase, row.expected, row.actual) for row in engine.compare(case)] == [
        ("turbohtml", "compilation", False, False),
        ("libxml2", "compilation", False, False),
        ("turbohtml", "validation", True, None),
        ("libxml2", "validation", True, None),
    ]


@pytest.mark.oracle
def test_xsd_inline_negative_control_changes_public_verdict(engine: ModuleType) -> None:
    case: Final = engine.generate(0)
    assert [
        (row.engine, row.phase, row.expected, row.actual) for row in engine.compare(case, negative_control=True)
    ] == [
        ("turbohtml", "compilation", True, True),
        ("libxml2", "compilation", True, True),
        ("turbohtml", "validation", True, False),
        ("libxml2", "validation", True, True),
        ("turbohtml", "validation", True, False),
        ("libxml2", "validation", True, True),
        ("turbohtml", "validation", False, True),
        ("libxml2", "validation", False, False),
    ]


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("arguments", "exit_status", "findings"),
    [
        pytest.param(["--cases", "8"], 0, 0, id="agreement"),
        pytest.param(["--cases", "8", "--negative-control"], 1, 18, id="wrong-verdict"),
    ],
)
def test_xsd_inline_cli(
    engine: ModuleType,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    exit_status: int,
    findings: int,
) -> None:
    assert engine.main(arguments) == exit_status
    rows: Final = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[-1] == {"summary": {"cases": 8, "rows": 52, "findings": findings}}
    assert {(row["engine"], row["phase"]) for row in rows[:-1]} == {
        ("turbohtml", "compilation"),
        ("libxml2", "compilation"),
        ("turbohtml", "validation"),
        ("libxml2", "validation"),
    }


@pytest.mark.oracle
@pytest.mark.parametrize("count", ["0", "257", "-1"])
def test_xsd_inline_cli_rejects_unbounded_cases(engine: ModuleType, count: str) -> None:
    with pytest.raises(SystemExit, match="2"):
        engine.main(["--cases", count])
