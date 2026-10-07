from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from types import ModuleType


@pytest.fixture
def engine() -> ModuleType:
    return pytest.importorskip("fuzz.rng_inline", exc_type=ImportError)


@pytest.mark.oracle
@pytest.mark.parametrize("seed", range(8))
def test_rng_inline_generated_labels(engine: ModuleType, seed: int) -> None:
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
def test_rng_inline_compile_verdicts(engine: ModuleType, schema: str) -> None:
    expected: Final = False
    case: Final = engine.Case(0, schema, expected, ())
    assert [(row.engine, row.phase, row.expected, row.actual) for row in engine.compare(case)] == [
        ("turbohtml", "compilation", expected, expected),
        ("libxml2", "compilation", expected, expected),
    ]


@pytest.mark.oracle
def test_rng_inline_unavailable_documents_remain_findings(engine: ModuleType) -> None:
    case: Final = engine.Case(0, "<", compiles=False, documents=(("<v/>", True),))
    assert [(row.engine, row.phase, row.expected, row.actual) for row in engine.compare(case)] == [
        ("turbohtml", "compilation", False, False),
        ("libxml2", "compilation", False, False),
        ("turbohtml", "validation", True, None),
        ("libxml2", "validation", True, None),
    ]


@pytest.mark.oracle
def test_rng_inline_negative_control_changes_public_verdict(engine: ModuleType) -> None:
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
def test_rng_inline_cli(
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
def test_rng_inline_cli_rejects_unbounded_cases(engine: ModuleType, count: str) -> None:
    with pytest.raises(SystemExit, match="2"):
        engine.main(["--cases", count])


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("pattern", "documents"),
    [
        pytest.param("<empty/>", (("<v/>", True), ("<v>wrong</v>", False)), id="group"),
        pytest.param(
            '<choice><value type="string">ok</value>{annotation}</choice>',
            (("<v>ok</v>", True), ("<v/>", False)),
            id="choice",
        ),
        pytest.param(
            "<interleave><empty/>{annotation}</interleave>",
            (("<v/>", True), ("<v>wrong</v>", False)),
            id="interleave",
        ),
        pytest.param(
            '<attribute name="key">{annotation}</attribute><empty/>',
            (('<v key="anything"/>', True), ("<v/>", False)),
            id="attribute-default-text",
        ),
    ],
)
def test_rng_inline_foreign_annotations_preserve_pattern_verdicts(
    engine: ModuleType,
    pattern: str,
    documents: tuple[tuple[str, bool], ...],
) -> None:
    annotation: Final = '<doc:annotation><ref name="missing"/></doc:annotation>'
    body: Final = pattern.replace("{annotation}", annotation)
    schema: Final = (
        '<grammar xmlns="http://relaxng.org/ns/structure/1.0" xmlns:doc="urn:documentation">'
        f'<start><element name="v">{body}{annotation}</element></start></grammar>'
    )
    case: Final = engine.Case(0, schema, compiles=True, documents=documents)
    assert [(row.engine, row.phase, row.expected, row.actual) for row in engine.compare(case)] == [
        ("turbohtml", "compilation", True, True),
        ("libxml2", "compilation", True, True),
        *[(name, "validation", expected, expected) for _, expected in documents for name in ("turbohtml", "libxml2")],
    ]


@pytest.mark.oracle
def test_rng_inline_foreign_annotation_preserves_explicit_name_class(engine: ModuleType) -> None:
    schema: Final = (
        '<element xmlns="http://relaxng.org/ns/structure/1.0" xmlns:doc="urn:documentation">'
        '<doc:annotation><ref name="missing"/></doc:annotation><name>v</name><empty/></element>'
    )
    case: Final = engine.Case(0, schema, compiles=True, documents=(("<v/>", True), ("<wrong/>", False)))
    assert [row.actual == row.expected for row in engine.compare(case)] == [True] * 6


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("pattern", "documents"),
    [
        pytest.param(
            '<element name="v"><interleave><element name="a"><empty/></element>'
            '<doc:annotation><element name="a"><empty/></element></doc:annotation>'
            '<element name="b"><empty/></element></interleave></element>',
            (("<v><a/><b/></v>", True), ("<v><a/><a/><b/></v>", False)),
            id="interleave-annotation-conflict",
        ),
        pytest.param(
            "<element><doc:annotation><name>wrong</name></doc:annotation><name>v</name><empty/></element>",
            (("<v/>", True), ("<wrong/>", False)),
            id="annotation-before-name-class",
        ),
    ],
)
def test_rng_inline_foreign_annotations_preserve_grammar_constraints(
    engine: ModuleType,
    pattern: str,
    documents: tuple[tuple[str, bool], ...],
) -> None:
    schema: Final = (
        '<grammar xmlns="http://relaxng.org/ns/structure/1.0" xmlns:doc="urn:documentation">'
        f"<start>{pattern}</start></grammar>"
    )
    case: Final = engine.Case(0, schema, compiles=True, documents=documents)
    assert [row.actual == row.expected for row in engine.compare(case)] == [True] * 6
