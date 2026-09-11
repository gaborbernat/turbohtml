from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS


@pytest.mark.parametrize(
    ("operation", "index"),
    [
        pytest.param("query-parents", 0, id="shared-parent"),
        pytest.param("query-parents", 1, id="distinct-parents"),
        pytest.param("query-closest", 1, id="distinct-ancestors"),
    ],
)
def test_pyquery_join_benchmark_output(operation: str, index: int) -> None:
    module: Final = pytest.importorskip("bench.competitors.pyquery", exc_type=ImportError)
    case: Final = cast("tuple[int, bool]", INPUTS[operation]()[index][1])
    count, shared = case
    assert [(node.tag, "".join(node.itertext())) for node in module.OPERATIONS[operation][0](case)] == (
        [("main", "x" * count)] if shared else [("main", "x")] * count
    )


def test_pyquery_closest_benchmark_rejects_duplicate_results() -> None:
    module: Final = pytest.importorskip("bench.competitors.pyquery", exc_type=ImportError)
    with pytest.raises(NotImplementedError, match="duplicate ancestors"):
        module.OPERATIONS["query-closest"][0](INPUTS["query-closest"]()[0][1])
