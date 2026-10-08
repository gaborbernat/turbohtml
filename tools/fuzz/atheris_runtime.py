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
    parser.add_argument("--sanitizer", type=Path, help="a static sanitizer runtime to merge in, as atheris does")
    arguments: Final = parser.parse_args(argv)
    build_runtime(arguments.archive, arguments.output, coverage=arguments.coverage, sanitizer=arguments.sanitizer)
    return 0


def build_runtime(archive: Path, output: Path, *, coverage: bool = False, sanitizer: Path | None = None) -> Path:
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
            *([] if sanitizer is None else [str(_shared_sanitizer(sanitizer, output))]),
            "-Wl,--no-whole-archive",
            "-ldl",
            "-pthread",
            *(["--coverage"] if coverage else []),
        ],
        check=True,
    )
    return library


def _shared_sanitizer(sanitizer: Path, output: Path) -> Path:
    # a preinit object registers the runtime through .preinit_array, which a shared object cannot carry; atheris drops
    # it the same way when it merges libFuzzer with a sanitizer (setup_utils/merge_libfuzzer_sanitizer.sh)
    merged: Final = output / "sanitizer.a"
    shutil.copyfile(sanitizer, merged)
    archiver: Final = os.environ.get("AR", "ar")
    members: Final = subprocess.run([archiver, "t", str(merged)], check=True, capture_output=True, text=True).stdout
    if preinit := [member for member in members.split() if "preinit" in member]:
        subprocess.run([archiver, "d", str(merged), *preinit], check=True)
    return merged


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
