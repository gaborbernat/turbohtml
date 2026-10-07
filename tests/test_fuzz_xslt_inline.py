from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from types import ModuleType


@pytest.fixture
def engines() -> tuple[ModuleType, ModuleType]:
    return (
        pytest.importorskip("fuzz.xslt_inline", exc_type=ImportError),
        pytest.importorskip("fuzz.schema_mutation", exc_type=ImportError),
    )


@pytest.mark.oracle
@pytest.mark.parametrize("seed", range(12))
def test_xslt_inline_generated_phase_labels(engines: tuple[ModuleType, ModuleType], seed: int) -> None:
    engine: Final = engines[0]
    case: Final = engine.generate(seed)
    rows: Final = list(engine.compare(case))
    assert [(row.engine, row.phase, row.actual == row.expected) for row in rows] == [
        (name, phase, True)
        for name in ("turbohtml", "libxslt")
        for phase in (("compilation", "application", "result") if case.applies else ("compilation", "application"))
    ]


@pytest.mark.oracle
@pytest.mark.parametrize("seed", [0, 7])
def test_xslt_inline_wrong_result_is_a_finding(engines: tuple[ModuleType, ModuleType], seed: int) -> None:
    engine: Final = engines[0]
    assert [
        (row.engine, row.phase)
        for row in engine.compare(engine.generate(seed), negative_control=True)
        if row.actual != row.expected
    ] == [
        ("turbohtml", "result"),
    ]


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("body", "output"),
    [
        pytest.param(
            '<out xmlns:p="urn:example" p:key="one"> alpha <child/> beta </out>',
            '<out xmlns:q="urn:example" q:key="one"> alpha <child/> beta </out>',
            id="expanded-names",
        ),
        pytest.param(
            '<out><x:comment>note</x:comment><x:processing-instruction name="go">now</x:processing-instruction></out>',
            "<out><!--note--><?go now?></out>",
            id="comment-and-instruction",
        ),
    ],
)
def test_xslt_inline_xml_content_is_preserved(engines: tuple[ModuleType, ModuleType], body: str, output: str) -> None:
    engine: Final = engines[0]
    stylesheet: Final = (
        '<x:stylesheet xmlns:x="http://www.w3.org/1999/XSL/Transform" version="1.0">'
        '<x:output method="xml"/><x:template match="/">' + body + "</x:template></x:stylesheet>"
    )
    case: Final = engine.Case(0, stylesheet, "<root/>", "xml", compiles=True, applies=True, output=output)
    assert [(row.engine, row.phase, row.actual == row.expected) for row in engine.compare(case)] == [
        (name, phase, True) for name in ("turbohtml", "libxslt") for phase in ("compilation", "application", "result")
    ]


@pytest.mark.oracle
def test_xslt_inline_malformed_stylesheet_retains_unavailable_application(
    engines: tuple[ModuleType, ModuleType],
) -> None:
    engine: Final = engines[0]
    case: Final = engine.Case(0, "<", "<root/>", "text", compiles=False, applies=False, output=None)
    assert [(row.engine, row.phase, row.expected, row.actual) for row in engine.compare(case)] == [
        ("turbohtml", "compilation", False, False),
        ("turbohtml", "application", None, None),
        ("libxslt", "compilation", False, False),
        ("libxslt", "application", None, None),
    ]


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        pytest.param([], (0, 0, 20), id="labelled-families"),
        pytest.param(["--negative-control"], (1, 10, 20), id="wrong-result"),
        pytest.param(["--mutate"], (0, 0, 24), id="repaired-subtrees"),
        pytest.param(["--mutate", "--broken-references"], (0, 0, 0), id="broken-references"),
    ],
)
def test_xslt_inline_cli_outcome_counts(
    engines: tuple[ModuleType, ModuleType],
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    expected: tuple[int, int, int],
) -> None:
    exit_status, findings, results = expected
    assert engines[0].main(arguments) == exit_status
    rows: Final = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[-1] == {
        "summary": {
            "cases": 12,
            "findings": findings,
            "phases": {"compilation": 24, "application": 24, **({"result": results} if results else {})},
        },
    }


@pytest.mark.oracle
@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param(["--cases", "0"], id="empty"),
        pytest.param(["--cases", "257"], id="too-many"),
        pytest.param(["--broken-references"], id="missing-mutation"),
    ],
)
def test_xslt_inline_cli_rejects_invalid_domain(
    engines: tuple[ModuleType, ModuleType],
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit, match="2"):
        engines[0].main(arguments)
