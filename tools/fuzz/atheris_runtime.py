"""Atheris's Python callback discards return values; libFuzzer needs native rejection."""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__ = ["build_runtime", "main", "rejecting_callback", "rejection_hook"]


def main(argv: Sequence[str] | None = None) -> int:
    """Build one ELF so libFuzzer and Atheris share coverage symbols."""
    parser: Final = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--coverage", action="store_true")
    arguments: Final = parser.parse_args(argv)
    build_runtime(arguments.archive, arguments.output, coverage=arguments.coverage)
    return 0


def build_runtime(archive: Path, output: Path, *, coverage: bool = False) -> Path:
    """Keep the original wheel archive intact for provenance checks."""
    output.mkdir(parents=True, exist_ok=True)
    runtime: Final = output / "runtime.a"
    shutil.copyfile(archive, runtime)
    subprocess.run(
        [
            os.environ.get("OBJCOPY", "objcopy"),
            "--redefine-sym",
            "LLVMFuzzerRunDriver=turbohtml_real_fuzzer_driver",
            str(runtime),
        ],
        check=True,
    )
    bridge: Final = output / "bridge.o"
    subprocess.run(
        [
            os.environ.get("CC", "gcc"),
            "-c",
            "-fPIC",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            *(["--coverage", "-DATHERIS_BRIDGE_COVERAGE"] if coverage else []),
            str(Path(__file__).with_name("atheris_bridge.c")),
            "-o",
            str(bridge),
        ],
        check=True,
    )
    library: Final = output / "libatheris_fuzzer.so"
    subprocess.run(
        [
            os.environ.get("CXX", "g++"),
            "-shared",
            "-o",
            str(library),
            str(bridge),
            "-Wl,--whole-archive",
            str(runtime),
            "-Wl,--no-whole-archive",
            "-ldl",
            "-pthread",
            *(["--coverage"] if coverage else []),
        ],
        check=True,
    )
    return library


def rejecting_callback(
    target: Callable[[bytes], None], exceptions: tuple[type[Exception], ...], reject: Callable[[], None]
) -> Callable[[bytes], None]:
    """Reject only exceptions the selected public API documents."""

    def run(data: bytes) -> None:
        try:
            target(data)
        except exceptions:
            reject()

    return run


def rejection_hook() -> Callable[[], None]:
    """Resolve the preloaded bridge before starting the callback loop."""
    return ctypes.CFUNCTYPE(None)(("turbohtml_fuzz_reject_input", ctypes.CDLL(None)))


if __name__ == "__main__":
    raise SystemExit(main())
