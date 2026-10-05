from __future__ import annotations

import json
import random
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.observer_oracles import (
    UnsupportedObserverCaseError,
    observer_sequence_check,
    observer_sequence_controls,
    observer_sequence_generate,
    observer_sequence_seeds,
)
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize("program", ["reuse1", "reuse2", "reuse3", "replace", "nested", "error"])
@pytest.mark.parametrize(
    "name",
    [
        pytest.param("g", id="distinct-tags"),
        pytest.param("b", id="same-child-tags"),
        pytest.param("div", id="same-root-tag"),
    ],
)
def test_observer_sequence_pins_edits_records_and_callbacks(program: str, name: str) -> None:
    case: Final = f"{program}:{name}"
    assert (
        observer_sequence_check(case),
        observer_sequence_check(case, lambda _program, _name: "[]"),
    ) == (None, "observer sequence differs from model")


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("reuse1", id="missing-separator"),
        pytest.param("unknown:g", id="unknown-program"),
        pytest.param("reuse0:g", id="unsupported-count"),
        pytest.param("reuse1:", id="empty-name"),
        pytest.param("reuse1:é", id="non-ascii-name"),
        pytest.param("reuse1:g<p>", id="markup-name"),
        pytest.param("reuse1:br", id="outside-nonvoid-fixtures"),
        pytest.param("reuse1:g" + "1" * 16, id="overlong-name"),
    ],
)
def test_observer_sequence_rejects_unsupported_grammar(case: str) -> None:
    with pytest.raises(UnsupportedObserverCaseError):
        observer_sequence_check(case)
    with pytest.raises(OutOfScopeError):
        ORACLES["observer-sequence"].check(case)


def test_observer_sequence_seed_programs_and_controls() -> None:
    rng: Final = random.SystemRandom()
    seeds: Final = observer_sequence_seeds()
    generated: Final = [observer_sequence_generate(rng) for _ in range(100)]
    assert (
        len(seeds),
        all(observer_sequence_check(case) is None for case in [*seeds, *generated]),
        observer_sequence_controls(),
    ) == (
        180,
        True,
        {"missing edit": True, "missing callback": True, "swallowed callback error": True},
    )


def test_observer_sequence_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "observer-sequence", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "180" in capsys.readouterr().out) == (0, [], True)


def test_observer_sequence_cli_emits_missed_edit(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["observer-sequence"],
        check=partial(observer_sequence_check, run=lambda _program, _name: "[]"),
        seeds=lambda: ["reuse1:a"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"observer-sequence": oracle}, clear=True)
    status: Final = main(["--oracle", "observer-sequence", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (
        1,
        1,
        "observer sequence differs from model",
        1,
    )


def test_observer_sequence_cli_emits_valid_program_failure(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["observer-sequence"],
        check=partial(observer_sequence_check, run=_reject_program),
        seeds=lambda: ["reuse1:a"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"observer-sequence": oracle}, clear=True)
    status: Final = main(["--oracle", "observer-sequence", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (1, 1, "raised RuntimeError", 1)


def _reject_program(_program: str, _name: str) -> str:
    message: Final = "valid DOM operation failed"
    raise RuntimeError(message)


def test_observer_sequence_cli_rejects_vacuous_run(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(
        ORACLES,
        {"observer-sequence": replace(ORACLES["observer-sequence"], seeds=lambda: ["unknown:g"], floor=Floor(1, 1))},
        clear=True,
    )
    assert main(["--oracle", "observer-sequence", "--minutes", "0", "--crash-dir", str(tmp_path)]) == 2
