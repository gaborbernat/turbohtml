from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

_PYQUERY: Final = pytest.importorskip("bench.competitors.pyquery", exc_type=ImportError)


@pytest.mark.parametrize(
    ("operation", "index"),
    [
        pytest.param("query-parents", 0, id="shared-parent"),
        pytest.param("query-parents", 1, id="distinct-parents"),
        pytest.param("query-closest", 1, id="distinct-ancestors"),
    ],
)
def test_pyquery_join_benchmark_output(operation: str, index: int) -> None:
    case: Final = cast("tuple[int, bool]", INPUTS[operation]()[index][1])
    count, shared = case
    assert [(node.tag, "".join(node.itertext())) for node in _PYQUERY.OPERATIONS[operation][0](case)] == (
        [("main", "x" * count)] if shared else [("main", "x")] * count
    )


def test_pyquery_closest_benchmark_rejects_duplicate_results() -> None:
    with pytest.raises(NotImplementedError, match="duplicate ancestors"):
        _PYQUERY.OPERATIONS["query-closest"][0](INPUTS["query-closest"]()[0][1])
