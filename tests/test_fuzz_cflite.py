from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.cflite import BUILD_IMAGE, RUN_IMAGE, main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from typing import IO
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


@pytest.fixture
def docker(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("fuzz.cflite.subprocess.run", autospec=True, return_value=mocker.MagicMock(returncode=0))


@pytest.fixture
def build_log(docker: MagicMock, mocker: MockerFixture) -> Callable[[str, int], None]:
    def write(log: str, returncode: int) -> None:
        def run(*_: object, stdout: IO[bytes], **__: object) -> MagicMock:
            stdout.write(log.encode())
            return mocker.MagicMock(returncode=returncode)

        docker.side_effect = run

    return write


def _arguments(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--mode",
        "batch",
        "--sanitizer",
        "address",
        "--seconds",
        "3600",
        "--source",
        str(tmp_path / "turbohtml"),
        "--workspace",
        str(tmp_path / "workspace"),
        *extra,
    ]


def test_cflite_runs_build_then_mode_on_standalone_filestore(docker: MagicMock, tmp_path: Path) -> None:
    assert main(_arguments(tmp_path)) == 0
    workspace: Final = tmp_path / "workspace"
    commands: Final = [call.args[0] for call in docker.call_args_list]
    assert [(command[-1], _environment(command)) for command in commands] == [
        (BUILD_IMAGE, _expected(tmp_path)),
        (RUN_IMAGE, {**_expected(tmp_path), "MODE": "batch", "FUZZ_SECONDS": "3600", "OUTPUT_SARIF": "True"}),
    ]
    assert commands[0][:9] == [
        "docker",
        "run",
        "--rm",
        "-v",
        "/var/run/docker.sock:/var/run/docker.sock",
        "-v",
        f"{workspace}:{workspace}",
        "-v",
        f"{tmp_path / 'turbohtml'}:{tmp_path / 'turbohtml'}",
    ]


def test_cflite_writes_logs_not_console(docker: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(_arguments(tmp_path))
    logs: Final = [call.kwargs["stdout"].name for call in docker.call_args_list]
    assert (logs, json.loads(capsys.readouterr().out)) == (
        [
            str(tmp_path / "workspace" / "logs" / "build-address.log"),
            str(tmp_path / "workspace" / "logs" / "batch-address.log"),
        ],
        {"crashes": [], "status": {"batch": 0, "build": 0}},
    )


def test_cflite_code_change_diffs_against_base(docker: MagicMock, tmp_path: Path) -> None:
    main(_arguments(tmp_path, "--base-ref", "main"))
    assert {_environment(call.args[0])["GIT_BASE_REF"] for call in docker.call_args_list} == {"main"}


def test_cflite_build_failure_skips_fuzzing(
    docker: MagicMock, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    docker.return_value = mocker.MagicMock(returncode=2)
    assert (main(_arguments(tmp_path)), docker.call_count, json.loads(capsys.readouterr().out)["status"]) == (
        2,
        1,
        {"build": 2},
    )


@pytest.mark.parametrize(
    ("log", "shown"),
    [
        pytest.param(
            "Step 1/4 : FROM base-builder-python\nERROR: meson setup failed\n",
            "Step 1/4 : FROM base-builder-python\nERROR: meson setup failed\n",
            id="build-step",
        ),
        pytest.param(
            "compile done\nBuild check: stdout: INFO: performing bad build checks for /out/fuzz_html_document\n"
            "BAD BUILD: /out/fuzz_html_document seems to have either startup crash or exit:\n"
            "==12==ERROR: AddressSanitizer: heap-buffer-overflow\nBase64: PHNlY3JldD4=\n"
            "2026-10-08 04:20:29,440 - root - ERROR - Build check failed.\n",
            "compile done\nBAD BUILD: /out/fuzz_html_document seems to have either startup crash or exit:\n"
            "2026-10-08 04:20:29,440 - root - ERROR - Build check failed.\n",
            id="bad-build-check-drops-fuzzer-output",
        ),
        pytest.param(
            "".join(f"line {index}\n" for index in range(250)),
            "".join(f"line {index}\n" for index in range(50, 250)),
            id="tail",
        ),
    ],
)
def test_cflite_build_failure_shows_public_build_log(
    build_log: Callable[[str, int], None], tmp_path: Path, capsys: pytest.CaptureFixture[str], log: str, shown: str
) -> None:
    build_log(log, 1)
    main(_arguments(tmp_path))
    assert capsys.readouterr().err == shown


def test_cflite_build_success_keeps_log_private(
    build_log: Callable[[str, int], None], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_log("compile done\n", 0)
    main(_arguments(tmp_path))
    assert not capsys.readouterr().err


def test_cflite_reports_crashes_by_hash(
    docker: MagicMock, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    crash: Final = tmp_path / "workspace" / "out" / "artifacts" / "fuzz_html_document" / "crash-input"
    crash.parent.mkdir(parents=True)
    crash.write_bytes(b"<secret>")
    docker.side_effect = [mocker.MagicMock(returncode=0), mocker.MagicMock(returncode=1)]
    status: Final = main(_arguments(tmp_path))
    output: Final = capsys.readouterr().out
    assert (status, json.loads(output)["crashes"], "secret" in output) == (
        1,
        [{"bytes": 8, "fuzzer": "fuzz_html_document", "sha256": hashlib.sha256(b"<secret>").hexdigest()}],
        False,
    )


def _environment(command: list[str]) -> dict[str, str]:
    return dict(command[index + 1].split("=", 1) for index, argument in enumerate(command) if argument == "-e")


def _expected(tmp_path: Path) -> dict[str, str]:
    return {
        "CFL_PLATFORM": "standalone",
        "WORKSPACE": str(tmp_path / "workspace"),
        "PROJECT_SRC_PATH": str(tmp_path / "turbohtml"),
        "REPOSITORY": "turbohtml",
        "FILESTORE": "filesystem",
        "FILESTORE_ROOT_DIR": str(tmp_path / "workspace" / "storage"),
        "LANGUAGE": "python",
        "SANITIZER": "address",
        "LOW_DISK_SPACE": "True",
    }
