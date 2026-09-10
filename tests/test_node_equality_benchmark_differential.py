from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import pytest
from bench.operations import INPUTS

if TYPE_CHECKING:
    from collections.abc import Callable


_BEAUTIFULSOUP: Final = pytest.importorskip("bench.competitors.beautifulsoup4", exc_type=ImportError)


def test_competitor_node_equality_duplicates_unsupported() -> None:
    operation: Final = cast("Callable[[tuple[int, str]], bool]", _BEAUTIFULSOUP.OPERATIONS["node-equals"][0])
    with pytest.raises(ValueError, match="constructor does not normalize case variants"):
        operation(cast("tuple[int, str]", INPUTS["node-equals"]()[12][1]))
