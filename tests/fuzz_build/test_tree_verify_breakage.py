"""The ``_fuzz_`` hooks exist in the fuzz build alone, which ``tox r -e fuzz-smoke`` runs this module against."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import _html

if TYPE_CHECKING:
    from collections.abc import Callable

# the stubs describe the production module, which lacks the hook
_VERIFY_BROKEN: Final[Callable[[str], tuple[int, int, int, int]]] = vars(_html)["_fuzz_verify_broken"]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        pytest.param("intact", (0, 0, 0, 0), id="intact"),
        pytest.param("sibling-cycle", (1, 0, 0, 0), id="sibling-cycle"),
        pytest.param("parent-mismatch", (1, 0, 0, 0), id="parent-mismatch"),
        pytest.param("foreign-child", (0, 1, 0, 0), id="foreign-child"),
        pytest.param("foreign-start", (0, 1, 0, 0), id="foreign-start"),
    ],
)
def test_tree_verify_reports_a_broken_tree_without_walking_into_it(
    kind: str, expected: tuple[int, int, int, int]
) -> None:
    assert _VERIFY_BROKEN(kind) == expected


def test_tree_verify_breakage_rejects_an_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown breakage"):
        _VERIFY_BROKEN("bogus")
