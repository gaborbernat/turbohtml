from __future__ import annotations

import json
import random
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.iterator_oracles import (
    UnsupportedIteratorCaseError,
    iterator_sequence_check,
    iterator_sequence_controls,
    iterator_sequence_generate,
    iterator_sequence_seeds,
)
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize("program", ["after", "before", "last", "ancestor"])
@pytest.mark.parametrize(
    "name",
    [
        pytest.param("g", id="distinct-tags"),
        pytest.param("b", id="same-first-tag"),
        pytest.param("div", id="ordinary-root"),
    ],
)
def test_iterator_sequence_pins_reference_and_traversal(program: str, name: str) -> None:
    case: Final = f"{program}:{name}"
    assert (
        iterator_sequence_check(case),
        iterator_sequence_check(case, lambda _program, _name: "[]"),
    ) == (None, "iterator sequence differs from model")


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("after", id="missing-separator"),
        pytest.param("unknown:g", id="unknown-program"),
        pytest.param("after0:g", id="unsupported-count"),
        pytest.param("after:", id="empty-name"),
        pytest.param("after:é", id="non-ascii-name"),
        pytest.param("after:g<p>", id="markup-name"),
        pytest.param("after:br", id="outside-nonvoid-fixtures"),
        pytest.param("after:g" + "1" * 16, id="overlong-name"),
    ],
)
def test_iterator_sequence_rejects_unsupported_grammar(case: str) -> None:
    with pytest.raises(UnsupportedIteratorCaseError):
        iterator_sequence_check(case)
    with pytest.raises(OutOfScopeError):
        ORACLES["iterator-sequence"].check(case)


def test_iterator_sequence_seed_programs_and_controls() -> None:
    rng: Final = random.SystemRandom()
    seeds: Final = iterator_sequence_seeds()
    generated: Final = [iterator_sequence_generate(rng) for _ in range(100)]
    assert (
        len(seeds),
        all(iterator_sequence_check(case) is None for case in [*seeds, *generated]),
        iterator_sequence_controls(),
    ) == (
        120,
        True,
        {"missing extraction": True, "stale reference": True, "wrong traversal order": True},
    )


def test_iterator_sequence_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "iterator-sequence", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "120" in capsys.readouterr().out) == (0, [], True)


def test_iterator_sequence_cli_emits_missed_edit(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["iterator-sequence"],
        check=partial(iterator_sequence_check, run=lambda _program, _name: "[]"),
        seeds=lambda: ["after:a"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"iterator-sequence": oracle}, clear=True)
    status: Final = main(["--oracle", "iterator-sequence", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (
        1,
        1,
        "iterator sequence differs from model",
        1,
    )


def test_iterator_sequence_cli_emits_valid_program_failure(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["iterator-sequence"],
        check=partial(iterator_sequence_check, run=_reject_program),
        seeds=lambda: ["after:a"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"iterator-sequence": oracle}, clear=True)
    status: Final = main(["--oracle", "iterator-sequence", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (1, 1, "raised RuntimeError", 1)


def _reject_program(_program: str, _name: str) -> str:
    message: Final = "valid DOM operation failed"
    raise RuntimeError(message)


def test_iterator_sequence_cli_rejects_vacuous_run(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(
        ORACLES,
        {"iterator-sequence": replace(ORACLES["iterator-sequence"], seeds=lambda: ["unknown:g"], floor=Floor(1, 1))},
        clear=True,
    )
    assert main(["--oracle", "iterator-sequence", "--minutes", "0", "--crash-dir", str(tmp_path)]) == 2
