from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from fuzz.fuzz import main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

_HEAP_REPORTS: Final = {"heap-buffer-overflow", "heap-use-after-free"}


def _runner(mocker: MockerFixture, crash: tuple[int, str | None], injection: int) -> Callable[..., MagicMock]:
    """Fake the children: a ``None`` crash report gives each kind the ASan report it expects."""
    code, stderr = crash

    def run(command: list[str], **_: object) -> MagicMock:
        script = command[2] if command[1:2] == ["-c"] else ""
        if "_fuzz_crash" in script:
            kind = command[3]
            report = f"ERROR: AddressSanitizer: {kind if kind in _HEAP_REPORTS else 'use-after-poison'} on address"
            return mocker.MagicMock(returncode=code, stdout="", stderr=report if stderr is None else stderr)
        if "_fuzz_inject_failure" in script:
            return mocker.MagicMock(returncode=injection, stdout="", stderr="")
        return mocker.MagicMock(returncode=0, stdout="runtime", stderr="")

    return run


@pytest.mark.parametrize(
    ("crash", "injection", "expected"),
    [
        pytest.param((-6, None), 0, 0, id="every-fault-reported"),
        pytest.param((0, ""), 0, 1, id="sanitizer-silent"),
        pytest.param((-11, "ERROR: AddressSanitizer: SEGV on unknown address"), 0, 1, id="unrelated-crash"),
        pytest.param((-6, None), 3, 3, id="injection-not-raised"),
    ],
)
def test_fuzz_smoke_self_test_gates_the_run(
    mocker: MockerFixture, tmp_path: Path, crash: tuple[int, str | None], injection: int, expected: int
) -> None:
    mocker.patch("fuzz.fuzz.subprocess.run", autospec=True, side_effect=_runner(mocker, crash, injection))
    assert main(["--mode", "smoke", "--crash-dir", str(tmp_path)]) == expected


def test_fuzz_smoke_self_test_skipped_without_inprocess(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch("fuzz.fuzz.subprocess.run", autospec=True, side_effect=_runner(mocker, (0, ""), 1))
    assert main(["--mode", "smoke", "--skip-inprocess", "--crash-dir", str(tmp_path)]) == 0
