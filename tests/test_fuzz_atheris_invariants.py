from __future__ import annotations

import pytest
from fuzz.atheris_invariants import assert_invariant
from fuzz.round_trip_oracles import OutOfScopeError


def test_atheris_invariant_raises_oracle_failure() -> None:
    with pytest.raises(AssertionError, match=r"^not a fixpoint$"):
        assert_invariant(lambda _text: "not a fixpoint", "x")


def test_atheris_invariant_skips_out_of_scope_case() -> None:
    def out_of_scope(text: str) -> str | None:
        raise OutOfScopeError(text)

    assert_invariant(out_of_scope, "x")


def test_atheris_invariant_passes_held_oracle() -> None:
    seen: list[str] = []
    assert_invariant(seen.append, "x")
    assert seen == ["x"]
