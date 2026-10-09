from __future__ import annotations

from typing import TYPE_CHECKING

from fuzz.fuzz import main

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


def test_fuzz_alloc_sweeps_only_the_inprocess_targets(mocker: MockerFixture, tmp_path: Path) -> None:
    reports = " ".join(
        f"ERROR: AddressSanitizer: {kind}"
        for kind in ("heap-buffer-overflow", "heap-use-after-free", "use-after-poison")
    )

    def run(command: list[str], **_: object) -> MagicMock:
        crashed = "_fuzz_crash" in (command[2] if command[1:2] == ["-c"] else "")
        return mocker.MagicMock(returncode=-6 if crashed else 0, stdout="runtime", stderr=reports)

    calls = mocker.patch("fuzz.fuzz.subprocess.run", autospec=True, side_effect=run).call_args_list
    assert main(["--mode", "alloc", "--crash-dir", str(tmp_path)]) == 0
    workers = [call.args[0][2:4] for call in calls if str(call.args[0][1]).endswith("_targets.py")]
    compiled = [call.args[0] for call in calls if "-fsanitize=address,undefined" in call.args[0]]
    assert (workers, compiled) == ([["--mode", "alloc"], ["--mode", "alloc"]], [])
