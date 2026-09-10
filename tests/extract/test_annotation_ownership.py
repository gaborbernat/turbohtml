from __future__ import annotations

from typing import Final

import pytest

from turbohtml import annotation_surface, annotation_tags


@pytest.mark.parametrize(
    "count", [pytest.param(1, id="one"), pytest.param(4, id="four"), pytest.param(32, id="thirty-two")]
)
def test_annotation_surface_owns_generator_labels(count: int) -> None:
    assert annotation_surface("a" * count, ((index, index + 1, f"label-{index:04d}") for index in range(count))) == {
        f"label-{index:04d}": ["a"] for index in range(count)
    }


@pytest.mark.parametrize(
    "count", [pytest.param(1, id="one"), pytest.param(4, id="four"), pytest.param(32, id="thirty-two")]
)
def test_annotation_tags_owns_generator_labels(count: int) -> None:
    expected: Final = "".join(f"<label-{index:04d}>a</label-{index:04d}>" for index in range(count))
    assert (
        annotation_tags("a" * count, ((index, index + 1, f"label-{index:04d}") for index in range(count))) == expected
    )
