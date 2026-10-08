from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from fuzz.fuzz import main

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("arguments", "flags"),
    [
        pytest.param(["--sanitizer", "address", "--skip-inprocess"], ["-fsanitize=address,undefined"], id="address"),
        # MemorySanitizer skips the extension without --skip-inprocess
        pytest.param(
            ["--sanitizer", "memory"], ["-fsanitize=memory", "-fsanitize-memory-track-origins=2"], id="memory"
        ),
    ],
)
def test_fuzz_cli_builds_every_standalone_harness_under_the_sanitizer(
    mocker: MockerFixture, tmp_path: Path, arguments: list[str], flags: list[str]
) -> None:
    run: Final = mocker.patch(
        "fuzz.fuzz.subprocess.run",
        autospec=True,
        return_value=mocker.MagicMock(returncode=0, stdout=str(tmp_path / "runtime")),
    )
    status: Final = main(["--mode", "smoke", *arguments, "--crash-dir", str(tmp_path / "crashes")])
    commands: Final = [call.args[0] for call in run.call_args_list]
    compiled: Final = [command for command in commands if "-o" in command]
    assert (
        status,
        [command[1] for command in compiled],
        all(command[2 : 2 + len(flags)] == flags for command in compiled),
        sum("_targets.py" in " ".join(command) for command in commands),
    ) == (
        0,
        ["-DTH_IDNA_STANDALONE", "-DTH_PHONE_STANDALONE", "-DJM_STANDALONE", "-DCSS_MINIFY_STANDALONE"],
        True,
        0,
    )
