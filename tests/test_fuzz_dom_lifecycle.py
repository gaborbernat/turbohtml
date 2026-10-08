from __future__ import annotations

import random
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.dom_lifecycle import (
    LifecycleStep,
    UnsupportedDomLifecycleError,
    dom_lifecycle_check,
    dom_lifecycle_controls,
    dom_lifecycle_generate,
    dom_lifecycle_seeds,
    run_dom_lifecycle,
)
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main

from turbohtml import Element, NodeFilter, NodeIterator, Text, parse
from turbohtml._html import _tree_verify

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from turbohtml import Node

_BROKEN: Final = ((LifecycleStep(0, "element", "ok", (0, 0, 1, 0)),), ())


def _steps(*instructions: tuple[int, int, int, int]) -> tuple[LifecycleStep, ...]:
    return run_dom_lifecycle(bytes(byte for instruction in instructions for byte in instruction))[0]


@pytest.mark.parametrize(
    "text", [pytest.param(seed, id=f"{index:03d}") for index, seed in enumerate(dom_lifecycle_seeds())]
)
def test_dom_lifecycle_seed_holds_and_reports_a_violation(text: str) -> None:
    assert (dom_lifecycle_check(text), dom_lifecycle_check(text, lambda _program: _BROKEN)) == (
        None,
        "tree invariant broken after element",
    )


def test_dom_lifecycle_generated_cases_hold() -> None:
    rng: Final = random.Random(1017)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - a fixed seed reproduces failing programs
    assert all(dom_lifecycle_check(dom_lifecycle_generate(rng)) is None for _ in range(100))


@pytest.mark.parametrize(
    ("report", "detail"),
    [
        pytest.param((0, 0, 0, 0), None, id="clean"),
        pytest.param((0, 0, 1, 0), "tree invariant broken after element", id="iterator"),
    ],
)
def test_dom_lifecycle_verifies_after_every_step(
    mocker: MockerFixture, report: tuple[int, ...], detail: str | None
) -> None:
    mocker.patch("fuzz.dom_lifecycle._tree_verify", return_value=report)
    assert dom_lifecycle_check(dom_lifecycle_seeds()[0]) == detail


def test_dom_lifecycle_negative_controls_fire() -> None:
    assert dom_lifecycle_controls() == {"missing violation": True, "replay drift": True}


@pytest.mark.parametrize(
    "text",
    [pytest.param("xx", id="not-hex"), pytest.param("0", id="odd-length"), pytest.param("00" * 1025, id="too-long")],
)
def test_dom_lifecycle_rejects_unsupported_encoding(text: str) -> None:
    with pytest.raises(UnsupportedDomLifecycleError):
        dom_lifecycle_check(text)
    with pytest.raises(OutOfScopeError):
        ORACLES["dom-lifecycle"].check(text)


def test_dom_lifecycle_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "dom-lifecycle", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "'compared': 224" in capsys.readouterr().out) == (0, [], True)


def test_dom_lifecycle_cli_emits_violation(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["dom-lifecycle"],
        check=partial(dom_lifecycle_check, run=lambda _program: _BROKEN),
        seeds=lambda: [dom_lifecycle_seeds()[0]],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"dom-lifecycle": oracle}, clear=True)
    status: Final = main(["--oracle", "dom-lifecycle", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, len(list(tmp_path.glob("*.json")))) == (1, 1)


def test_dom_lifecycle_empty_program_keeps_empty_registers() -> None:
    assert run_dom_lifecycle(b"") == ((), ("",) * 8)


def test_dom_lifecycle_partial_instruction_is_ignored() -> None:
    assert run_dom_lifecycle(bytes((0, 0, 0, 0, 1, 2))) == run_dom_lifecycle(bytes((0, 0, 0, 0)))


def test_dom_lifecycle_limits_executed_steps() -> None:
    assert len(_steps(*[(1, 0, 0, 0)] * 300)) == 256


def test_dom_lifecycle_limits_created_nodes() -> None:
    assert [step.outcome for step in _steps(*[(0, 0, 0, 0)] * 50)][47:] == ["ok", "cap", "cap"]


def test_dom_lifecycle_bounds_callback_nesting() -> None:
    steps: Final = _steps((18, 0, 0, 3), (18, 0, 0, 2), (18, 0, 0, 1), (0, 0, 0, 0))
    assert max(step.depth for step in steps) == 2


@pytest.mark.parametrize(
    ("instructions", "outcome"),
    [
        pytest.param([(27, 0, 0, 0)], "abort", id="top-level"),
        pytest.param([(18, 0, 0, 1), (27, 0, 0, 0)], "_UnwindError", id="from-callback"),
    ],
)
def test_dom_lifecycle_raise_unwinds_to_the_enclosing_operation(
    instructions: list[tuple[int, int, int, int]], outcome: str
) -> None:
    assert _steps(*instructions)[-1].outcome == outcome


@pytest.mark.parametrize(
    ("instructions", "outcome"),
    [
        pytest.param([(0, 0, 0, 0), (0, 1, 0, 0), (4, 0, 1, 0), (6, 1, 0, 0)], "ok", id="extract-retained"),
        pytest.param([(0, 0, 0, 0), (0, 1, 0, 0), (4, 0, 1, 0), (8, 0, 0, 0)], "ValueError", id="unwrap-root"),
        pytest.param([(1, 0, 0, 0), (4, 0, 0, 0)], "empty", id="append-to-text"),
        pytest.param([(19, 0, 0, 0), (21, 0, 0, 0), (14, 0, 0, 0)], "ok", id="token-iterator-step"),
    ],
)
def test_dom_lifecycle_operation_outcome(instructions: list[tuple[int, int, int, int]], outcome: str) -> None:
    assert _steps(*instructions)[-1].outcome == outcome


def test_tree_verify_keeps_an_iterator_reference_inside_its_root_across_normalize() -> None:
    root: Final = Element("div", children=[Text("x"), Text("y")])
    iterator: Final = NodeIterator(root)
    for _ in range(3):
        iterator.next_node()
    root.normalize()  # merging removes the reference, so the removal steps move it back to the merged text
    assert (_tree_verify(root), iterator.reference_node) == ((0, 0, 0, 0), root.children[0])


def test_tree_verify_keeps_a_filter_candidate_inside_its_root_across_normalize() -> None:
    merged: Final = Text("y")
    root: Final = Element("div", children=[Text("x"), merged])
    reports: Final[list[tuple[int, int, int, int]]] = []

    def record(node: Node) -> int:
        if node == merged:
            # merging removes the candidate, so the removal steps move it back to the merged text
            root.normalize()
            reports.append(_tree_verify(root))
        return NodeFilter.FILTER_SKIP

    assert (list(NodeIterator(root, filter=record)), reports) == ([], [(0, 0, 0, 0)])


def test_tree_verify_accepts_a_current_css_path_id_map() -> None:
    document: Final = parse('<p id="a"><b></b></p>')
    document.select("b")[0].css_path()
    assert _tree_verify(document) == (0, 0, 0, 0)


def test_tree_verify_rejects_a_non_node() -> None:
    with pytest.raises(TypeError, match="expected a turbohtml element"):
        _tree_verify(object())  # ty: ignore[invalid-argument-type] - the hook validates its argument at runtime
