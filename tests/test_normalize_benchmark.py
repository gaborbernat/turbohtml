from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest
from bench.ci import benchmarks
from bench.core import OPERATIONS

if TYPE_CHECKING:
    from bench.timing import Mutating

    from turbohtml import Element


@pytest.mark.parametrize("count", [2, 10], ids=["pair", "run"])
def test_normalize_benchmark_rebuilds_input(count: int) -> None:
    operation: Final = cast("Mutating", OPERATIONS["normalize-dom"][0])
    root: Final = cast("Element", operation.setup((count, "é😀")))
    untouched: Final = cast("Element", operation.setup((count, "é😀")))
    operation.run(root)
    assert ([child.text for child in root], [child.text for child in untouched]) == (["é😀" * count], ["é😀"] * count)


def test_empty_tail_benchmark_preserves_first_node() -> None:
    _, run, load = next(benchmark for benchmark in benchmarks() if benchmark[0] == "normalize-dom-empty-tail")
    operation: Final = cast("Mutating", run)
    root: Final = cast("Element", operation.setup(load()))
    before: Final = tuple(root)
    operation.run(root)
    assert (tuple(root), tuple(node.text for node in before), [node.parent for node in before[1:]]) == (
        (before[0],),
        ("word", *("",) * 1000),
        [None] * 1000,
    )
