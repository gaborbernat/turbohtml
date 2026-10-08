"""OSS-Fuzz and ClusterFuzzLite package each registry target as its own Atheris fuzzer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from .atheris_targets import public_targets

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["atheris_target_names", "fuzzer_name", "main", "write_harnesses"]

# the javascript target checks the minifier against acorn and eslint-scope running in Node, which the OSS-Fuzz runner
# image does not carry; build.sh fuzzes the same engine through the native js_minify harness instead
_NEEDS_NODE: Final = frozenset({"javascript"})
_ENTRY: Final = """import sys

from fuzz.atheris_driver import fuzz
from fuzz.atheris_targets import MODULES, public_targets

fuzz(public_targets(), MODULES, {name!r}, sys.argv)
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Print each written script so build.sh packages exactly the registry's targets."""
    parser: Final = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["harnesses"])
    parser.add_argument("--output", type=Path, required=True)
    arguments: Final = parser.parse_args(argv)
    for path in write_harnesses(arguments.output):
        print(path)
    return 0


def write_harnesses(output: Path) -> list[Path]:
    """Write one script per target; compile_python_fuzzer packages each into its own fuzzer."""
    output.mkdir(parents=True, exist_ok=True)
    paths: Final[list[Path]] = []
    for name in atheris_target_names():
        path = output / f"{fuzzer_name(name)}.py"
        path.write_text(_ENTRY.format(name=name), encoding="utf-8")
        paths.append(path)
    return paths


def fuzzer_name(target: str) -> str:
    """Name the entry script, and so the fuzzer OSS-Fuzz derives from it, as a Python identifier."""
    return "fuzz_" + target.replace("-", "_")


def atheris_target_names() -> tuple[str, ...]:
    """Every registered Atheris target the runner image can execute."""
    return tuple(target.name for target in public_targets() if target.name not in _NEEDS_NODE)


if __name__ == "__main__":
    sys.exit(main())
