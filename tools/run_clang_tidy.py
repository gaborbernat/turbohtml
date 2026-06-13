#!/usr/bin/env python3
"""
Run clang-tidy over the C extension for the pre-commit hook.

clang-tidy needs a compile database, which Meson produces at configure time. We
keep a throwaway build directory under ``build/`` (git-ignored) and configure it
once; later runs reuse it. Only the ``.c`` translation units are analyzed; the
``.h`` files (including the implementation fragments some ``.c`` files #include)
are pulled in by those and checked through the header filter in ``.clang-tidy``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "clang-tidy"


def compile_database() -> Path:
    """Configure the Meson build directory once and return it."""
    if not (BUILD / "compile_commands.json").exists():
        subprocess.run(["meson", "setup", str(BUILD), "--buildtype=plain"], cwd=ROOT, check=True)
    return BUILD


def main(argv: list[str]) -> int:
    """Run clang-tidy over the ``.c`` paths in ``argv``; return its exit code."""
    sources = [arg for arg in argv if arg.endswith(".c")]
    if not sources:
        return 0
    command = ["clang-tidy", f"-p={compile_database()}"]
    if sys.platform == "darwin":
        # the bundled clang-tidy resolves system headers against the macOS SDK only
        # when told where it lives; Linux finds them on the default search path
        sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True, check=True)
        command += ["--extra-arg=-isysroot", f"--extra-arg={sdk.stdout.strip()}"]
    return subprocess.run([*command, *sources], cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
