from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest
from bench.core import OPERATIONS

if TYPE_CHECKING:
    from bench.timing import Mutating

    from turbohtml import Element


@pytest.mark.parametrize("existing", [False, True], ids=["new", "replacement"])
def test_attribute_benchmark_rebuilds_input(*, existing: bool) -> None:
    operation: Final = cast("Mutating", OPERATIONS["attribute-grow"][0])
    case: Final = cast("tuple[Element, tuple[str, ...]]", operation.setup((3, existing)))
    untouched: Final = cast("tuple[Element, tuple[str, ...]]", operation.setup((3, existing)))
    operation.run(case)
    assert (dict(case[0].attrs), dict(untouched[0].attrs)) == (
        {f"data-{index}": "after" for index in range(3)},
        {f"data-{index}": "before" for index in range(3)} if existing else {},
    )
