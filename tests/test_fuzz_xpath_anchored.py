"""Nonempty selections and a real engine control prevent vacuous differentials."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from types import ModuleType

    from pytest_mock import MockerFixture

_XML: Final = '<root id="n0"><item id="n1" score="2">alpha</item><item id="n2" score="5">beta</item></root>'


@pytest.fixture
def anchored() -> ModuleType:
    return pytest.importorskip("fuzz.xpath_anchored", exc_type=ImportError)


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("predicate", "target", "expected"),
    [
        pytest.param("@score < 3", "n1", ("n1",), id="retained-true"),
        pytest.param("@score < 3", "n2", ("n2",), id="negated-false"),
        pytest.param("position()=1", "n2", ("n2",), id="selection-position-context"),
        pytest.param("count(child::*)", "n1", ("n1", "n2"), id="numeric-boolean-conversion"),
        pytest.param("@missing", "n1", ("n1", "n2"), id="empty-node-set"),
    ],
)
def test_xpath_anchored_retains_target(
    anchored: ModuleType, predicate: str, target: str, expected: tuple[str, ...]
) -> None:
    verdict: Final = next(anchored.compare(anchored.Case(_XML, target, predicate)))
    assert (verdict.ours, verdict.reference) == (("nodes", expected), ("nodes", expected))


@pytest.mark.oracle
def test_xpath_anchored_compares_values_and_types(anchored: ModuleType) -> None:
    rows: Final = list(anchored.compare(anchored.Case(_XML, "n1", "@score < 3")))
    assert [(row.ours, row.reference) for row in rows] == [
        (("nodes", ("n1",)), ("nodes", ("n1",))),
        (("nodes", ("n1",)), ("nodes", ("n1",))),
        (("nodes", ("alpha",)), ("nodes", ("alpha",))),
        (("number", 1.0), ("number", 1.0)),
        (("boolean", True), ("boolean", True)),
        (("string", "alpha"), ("string", "alpha")),
    ]


@pytest.mark.oracle
def test_xpath_anchored_reports_evaluation_rejection(anchored: ModuleType) -> None:
    assert [(row.ours, row.reference) for row in anchored.compare(anchored.Case(_XML, "n1", "unknown()"))] == [
        (("error", "evaluation"), ("error", "evaluation"))
    ] * 6


@pytest.mark.oracle
def test_xpath_anchored_control_changes_actual_boolean_answer(anchored: ModuleType) -> None:
    rows: Final = list(anchored.compare(anchored.Case(_XML, "n1", "@score < 3"), negative_control=True))
    assert [(row.ours, row.reference) for row in rows if row.ours != row.reference] == [
        (("boolean", False), ("boolean", True))
    ]


@pytest.mark.oracle
@pytest.mark.parametrize(
    "seed",
    [
        pytest.param(0, id="first"),
        pytest.param(1, id="second"),
        pytest.param(7, id="root-target"),
        pytest.param(42, id="later-seed"),
    ],
)
def test_xpath_anchored_generation_is_deterministic_and_bounded(anchored: ModuleType, seed: int) -> None:
    case: Final = anchored.generate(seed)
    etree: Final = pytest.importorskip("lxml.etree")
    elements: Final = list(etree.fromstring(case.xml.encode()).iter())
    identifiers: Final = [element.get("id") for element in elements]
    assert (
        case == anchored.generate(seed),
        case != anchored.generate(seed + 1),
        case.seed,
        8 <= len(elements) <= 16,
        len(set(identifiers)),
        case.target in identifiers,
    ) == (
        True,
        True,
        seed,
        True,
        len(elements),
        True,
    )


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("control", "expected_status", "findings"),
    [pytest.param(False, 0, 0, id="agreement"), pytest.param(True, 1, 2, id="actual-engine-control")],
)
def test_xpath_anchored_cli_summary(
    anchored: ModuleType, capsys: pytest.CaptureFixture[str], *, control: bool, expected_status: int, findings: int
) -> None:
    arguments: Final = ["--seed", "0", "--cases", "2"] + (["--negative-control"] if control else [])
    status: Final = anchored.main(arguments)
    assert (status, json.loads(capsys.readouterr().out.splitlines()[-1])) == (
        expected_status,
        {"summary": {"cases": 2, "rows": 12, "findings": findings}},
    )


@pytest.mark.oracle
@pytest.mark.parametrize("count", [pytest.param("0", id="empty"), pytest.param("257", id="over-limit")])
def test_xpath_anchored_cli_rejects_unbounded_batches(anchored: ModuleType, count: str) -> None:
    with pytest.raises(SystemExit) as error:
        anchored.main(["--cases", count])
    assert error.value.code == 2


@pytest.mark.oracle
@pytest.mark.usefixtures("anchored")
def test_xpath_anchored_script_entry(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    mocker.patch("sys.argv", ["xpath_anchored.py", "--cases", "1"])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(__file__).parents[1] / "tools" / "fuzz" / "xpath_anchored.py"), run_name="__main__")
    assert (error.value.code, json.loads(capsys.readouterr().out.splitlines()[-1])) == (
        0,
        {"summary": {"cases": 1, "rows": 6, "findings": 0}},
    )
