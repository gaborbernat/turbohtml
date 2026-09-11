"""CodSpeed benchmarks driven off the shared ``bench`` registry.

The cases come from :func:`bench.ci.benchmarks`, which walks the same :data:`bench.core.OPERATIONS` the pyperf suite
times over the same real corpora, so each tracked operation gets an instruction-count regression gate in CI. Selected
operations register a second input when one case cannot cover the relevant branch patterns. The benchmarks run only
under ``--codspeed`` (see ``conftest.py``): the CI benchmark job passes it, and locally it is opt-in. Mutating
operations rebuild their tree through the pedantic ``setup`` hook, which runs untimed before each measured call, so the
number is the mutation and not the parse. A case whose corpus is not checked out fails loudly rather than skipping, so
a benchmark run can never silently measure nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import generate_normalize
import pytest
from bench.ci import benchmarks
from bench.corpus import large_text
from bench.timing import Mutating

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_codspeed import BenchmarkFixture
    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("operation", "load"),
    [pytest.param(run, load, id=name) for name, run, load in benchmarks()],
)
def test_feature(benchmark: BenchmarkFixture, operation: object, load: Callable[[], object]) -> None:
    try:
        case = load()
    except OSError as exc:
        # this body runs only under --codspeed (conftest skips it otherwise), so a missing corpus is a hard error
        msg = f"bench corpus submodule not checked out: {exc}; run: git submodule update --init tools/bench-data"
        raise RuntimeError(msg) from exc
    if isinstance(operation, Mutating):
        benchmark.pedantic(operation.run, setup=lambda: ((operation.setup(case),), {}))
    else:
        benchmark(cast("Callable[[object], object]", operation), case)


def test_generate_normalization(benchmark: BenchmarkFixture, mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch(
        "generate_normalize.fetch_bytes",
        return_value=large_text(
            "DerivedNormalizationProps-16.0.0.txt",
            "https://www.unicode.org/Public/16.0.0/ucd/DerivedNormalizationProps.txt",
        ).encode("utf-8"),
    )
    output: Final = tmp_path / "normalize_table.h"
    benchmark(generate_normalize.generate, output)
    assert output.read_bytes() == (Path(__file__).parents[2] / "src/turbohtml/_c/data/normalize_table.h").read_bytes()
