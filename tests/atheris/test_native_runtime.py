from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from subprocess import run  # ruff: ignore[suspicious-subprocess-import] - libFuzzer needs a separate process.
from typing import TYPE_CHECKING, Final, cast

import pytest
from fuzz.atheris_header import HEADER_SIZE, SEED_HEADER
from fuzz.atheris_runtime import build_runtime

if TYPE_CHECKING:
    from typing import Protocol

    class _Runtime(Protocol):
        def path(self) -> str: ...


_TARGET: Final = """
from __future__ import annotations

import ctypes
import os
from typing import Final

__all__ = ["consume"]
_MODE: Final = os.environ["ATHERIS_CONTROL_MODE"]
_VISITS: Final = [0]
_DUMP: Final = ctypes.CFUNCTYPE(None)(("turbohtml_fuzz_dump_coverage", ctypes.CDLL(None)))


def consume(data: bytes) -> None:
    _VISITS[0] += 1
    if _VISITS[0] == 63:
        _DUMP()
    if _MODE == "reset" and _VISITS[0] == 1:
        raise UnicodeError("documented initial control")
    if _MODE == "unexpected":
        raise RuntimeError("unexpected control")
    if data == b"BENIGN_A":
        if _MODE in {"reject", "mixed"}:
            raise UnicodeError("documented control")
    elif data == b"BENIGN_B" and _MODE == "reject":
        raise UnicodeError("documented control")
"""

_CHILD: Final = """
from __future__ import annotations

import sys
from pathlib import Path

from capability_target import consume
from fuzz.atheris_driver import fuzz
from fuzz.atheris_registry import Target


def mutate(data: bytes, max_size: int, seed: int) -> bytes:
    if sys.argv[2] == "reset":
        return b"BENIGN_B"[:max_size]
    return (b"BENIGN_A", b"BENIGN_B")[seed % 2][:max_size]


fuzz(
    [Target("benign", consume, ("capability_target.consume",), (UnicodeError,))],
    ["capability_target"],
    "benign",
    [
        sys.argv[0],
        sys.argv[1],
        sys.argv[3],
        "-atheris_runs=64",
        "-seed=1",
        "-max_len=32",
        "-artifact_prefix=" + sys.argv[1] + "/",
    ],
    custom_mutator=None if sys.argv[2] == "default" else mutate,
)
"""


@pytest.mark.oracle
def test_atheris_native_corpus_rejection(tmp_path: Path) -> None:
    if sys.platform != "linux" or importlib.util.find_spec("atheris") is None:
        pytest.skip("Atheris's released runtime requires Linux and its optional wheel")
    runtime = cast("_Runtime", importlib.import_module("atheris"))
    archive = Path(runtime.path()) / "libclang_rt.fuzzer_no_main.a"
    library = build_runtime(archive, tmp_path / "build", coverage=True)
    (tmp_path / "capability_target.py").write_text(_TARGET, encoding="utf-8")
    child = tmp_path / "child.py"
    child.write_text(_CHILD, encoding="utf-8")
    environment = {
        **os.environ,
        "LD_PRELOAD": str(library),
        "PYTHONPATH": os.pathsep.join((str(tmp_path), str(Path(__file__).parents[2] / "tools"))),
    }
    # libFuzzer reads the seed directory but writes only new units, to the first directory
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "seed").write_bytes(SEED_HEADER + b"SEED")
    corpora: dict[str, list[str]] = {}
    for mode in ("accept", "reject", "mixed", "reset", "default", "unexpected"):
        corpus = tmp_path / f"{mode}-corpus"
        corpus.mkdir()
        result = run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed interpreter and local control.
            [sys.executable, str(child), str(corpus), mode, str(seeds)],
            env={**environment, "ATHERIS_CONTROL_MODE": mode},
            capture_output=True,
            check=False,
        )
        (tmp_path / f"{mode}.log").write_bytes(result.stdout + result.stderr)
        assert b"ATHERIS_REJECTION_BRIDGE=1" in result.stderr
        assert b"Coverage symbols are being provided by a library other than libFuzzer" not in result.stderr
        if mode == "unexpected":
            assert result.returncode != 0
            assert b"RuntimeError: unexpected control" in result.stdout + result.stderr
        else:
            assert result.returncode == 0
            assert b"Done 64" in result.stderr
            if mode != "default":
                assert b"ATHERIS_CUSTOM_MUTATOR_BRIDGE=1" in result.stderr
                corpora[mode] = sorted({path.read_bytes()[HEADER_SIZE:].decode("ascii") for path in corpus.iterdir()})
    (tmp_path / "corpora.json").write_text(json.dumps(corpora), encoding="utf-8")
    assert corpora == {"accept": ["BENIGN_A", "BENIGN_B"], "reject": [], "mixed": ["BENIGN_B"], "reset": ["BENIGN_B"]}
