from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import pytest
from fuzz.atheris_header import SEED_HEADER, Header
from fuzz.atheris_runtime import build_runtime, failure_hook, main, rejecting_callback, rejection_hook

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

    def consume(data: bytes, _header: Header) -> None:
        if data == b"invalid":
            message = "documented error"
            raise UnicodeError(message)
        accepted.append(data)

    callback = rejecting_callback(consume, (UnicodeError,), partial(rejected.append, 1), lambda _position: (0, False))
    callback(SEED_HEADER + b"invalid")
    callback(SEED_HEADER + b"valid")
    assert (accepted, rejected) == ([b"valid"], [1])


def test_atheris_callback_preserves_unexpected_error() -> None:
    rejected: list[int] = []

    def consume(data: bytes, _header: Header) -> None:
        raise ValueError(data.decode())

    callback = rejecting_callback(consume, (UnicodeError,), partial(rejected.append, 1), lambda _position: (0, False))
    with pytest.raises(ValueError, match="unexpected"):
        callback(SEED_HEADER + b"unexpected")
    assert rejected == []


def test_atheris_callback_opens_and_closes_failure_window(mocker: MockerFixture) -> None:
    inject = mocker.MagicMock(return_value=(3, False))
    target = mocker.MagicMock()
    rejecting_callback(target, (), mocker.MagicMock(), inject)(Header(2, 7, 1).encode() + b"x")
    assert (inject.call_args_list, target.call_args_list) == (
        [mocker.call(7), mocker.call(0)],
        [mocker.call(b"x", Header(2, 7, 1))],
    )


def test_atheris_callback_keeps_injected_memory_error(mocker: MockerFixture) -> None:
    def consume(_data: bytes, _header: Header) -> None:
        raise MemoryError

    reject = mocker.MagicMock()
    rejecting_callback(consume, (UnicodeError,), reject, lambda _position: (1, True))(SEED_HEADER)
    assert reject.call_count == 0


@pytest.mark.parametrize(
    ("raised", "failed", "error", "match"),
    [
        pytest.param(MemoryError, False, MemoryError, "^$", id="uninjected-memory-error"),
        pytest.param(None, True, AssertionError, "^a result for an injected", id="injected-result"),
        pytest.param(UnicodeError, True, AssertionError, "^UnicodeError for an injected", id="injected-documented"),
    ],
)
def test_atheris_callback_reports_failure_mismatch(
    mocker: MockerFixture, raised: type[Exception] | None, error: type[Exception], match: str, *, failed: bool
) -> None:
    def consume(_data: bytes, _header: Header) -> None:
        if raised is not None:
            raise raised

    reject = mocker.MagicMock()
    callback = rejecting_callback(consume, (UnicodeError,), reject, lambda _position: (1, failed))
    with pytest.raises(error, match=match):
        callback(SEED_HEADER)
    assert reject.call_count == 0


def test_atheris_rejection_hook_propagates_loader_error(mocker: MockerFixture) -> None:
    mocker.patch("ctypes.CDLL", autospec=True, side_effect=OSError("loader failed"))
    with pytest.raises(OSError, match="loader failed"):
        rejection_hook()


def test_atheris_failure_hook_requires_fuzzing_build() -> None:
    with pytest.raises(KeyError, match="_fuzz_inject_failure"):
        failure_hook()
