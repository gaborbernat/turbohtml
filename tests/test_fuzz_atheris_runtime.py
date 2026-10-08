from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import pytest
from fuzz.atheris_runtime import build_runtime, main, rejecting_callback, rejection_hook

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize("instrumented", [pytest.param(False, id="release"), pytest.param(True, id="coverage")])
@pytest.mark.parametrize("via_cli", [pytest.param(False, id="build"), pytest.param(True, id="cli")])
def test_atheris_runtime_build_keeps_archive(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, via_cli: bool, instrumented: bool
) -> None:
    archive = tmp_path / "wheel-runtime.a"
    archive.write_bytes(b"original archive")
    for name in ("CC", "CXX", "OBJCOPY"):
        monkeypatch.delenv(name, raising=False)
    output = tmp_path / "built"
    run = mocker.patch("subprocess.run", autospec=True, return_value=None)
    if via_cli:
        assert (
            main(["--archive", str(archive), "--output", str(output), *(["--coverage"] if instrumented else [])]) == 0
        )
    else:
        assert build_runtime(archive, output, coverage=instrumented) == output / "libatheris_fuzzer.so"
    commands = [call.args[0] for call in run.call_args_list]
    assert (archive.read_bytes(), (output / "runtime.a").read_bytes(), len(commands), commands[0], commands[2]) == (
        b"original archive",
        b"original archive",
        3,
        [
            "objcopy",
            "--redefine-sym",
            "LLVMFuzzerRunDriver=turbohtml_real_fuzzer_driver",
            str(output / "runtime.a"),
        ],
        [
            "g++",
            "-shared",
            "-o",
            str(output / "libatheris_fuzzer.so"),
            str(output / "bridge.o"),
            "-Wl,--whole-archive",
            str(output / "runtime.a"),
            "-Wl,--no-whole-archive",
            "-ldl",
            "-pthread",
            *(["--coverage"] if instrumented else []),
        ],
    )


@pytest.mark.parametrize(
    ("members", "deleted"),
    [
        pytest.param("asan_rtl.cpp.o\nasan_preinit.cpp.o\n", ["asan_preinit.cpp.o"], id="preinit"),
        pytest.param("ubsan_handlers.cpp.o\n", None, id="no-preinit"),
    ],
)
def test_atheris_runtime_merges_sanitizer_without_preinit(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, members: str, deleted: list[str] | None
) -> None:
    archive = tmp_path / "wheel-runtime.a"
    archive.write_bytes(b"original archive")
    sanitizer = tmp_path / "libclang_rt.asan.a"
    sanitizer.write_bytes(b"sanitizer archive")
    monkeypatch.delenv("AR", raising=False)
    output = tmp_path / "built"
    run = mocker.patch("subprocess.run", autospec=True, return_value=mocker.MagicMock(stdout=members))
    assert main(["--archive", str(archive), "--output", str(output), "--sanitizer", str(sanitizer)]) == 0
    commands = [call.args[0] for call in run.call_args_list]
    merged = str(output / "sanitizer.a")
    assert (sanitizer.read_bytes(), (output / "sanitizer.a").read_bytes(), commands[2:-1], commands[-1][6:9]) == (
        b"sanitizer archive",
        b"sanitizer archive",
        [["ar", "t", merged], *([] if deleted is None else [["ar", "d", merged, *deleted]])],
        [str(output / "runtime.a"), merged, "-Wl,--no-whole-archive"],
    )


def test_atheris_runtime_build_propagates_compiler_failure(mocker: MockerFixture, tmp_path: Path) -> None:
    archive = tmp_path / "wheel-runtime.a"
    archive.write_bytes(b"original archive")
    failure = OSError("compiler unavailable")
    mocker.patch("subprocess.run", autospec=True, side_effect=failure)
    with pytest.raises(OSError, match="compiler unavailable") as raised:
        build_runtime(archive, tmp_path / "built")
    assert raised.value is failure


def test_atheris_callback_rejects_documented_error() -> None:
    accepted: list[bytes] = []
    rejected: list[int] = []

    def consume(data: bytes) -> None:
        if data == b"invalid":
            message = "documented error"
            raise UnicodeError(message)
        accepted.append(data)

    callback = rejecting_callback(consume, (UnicodeError,), partial(rejected.append, 1))
    callback(b"invalid")
    callback(b"valid")
    assert (accepted, rejected) == ([b"valid"], [1])


def test_atheris_callback_preserves_unexpected_error() -> None:
    rejected: list[int] = []

    def consume(data: bytes) -> None:
        raise ValueError(data.decode())

    callback = rejecting_callback(consume, (UnicodeError,), partial(rejected.append, 1))
    with pytest.raises(ValueError, match="unexpected"):
        callback(b"unexpected")
    assert rejected == []


def test_atheris_rejection_hook_propagates_loader_error(mocker: MockerFixture) -> None:
    mocker.patch("ctypes.CDLL", autospec=True, side_effect=OSError("loader failed"))
    with pytest.raises(OSError, match="loader failed"):
        rejection_hook()
