from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

# only the fuzz-only build (meson -Dfuzzing=true) defines the hook, so the stubs omit it
_HOOKS: Final = vars(importlib.import_module("turbohtml._html"))


@pytest.fixture
def alloc_sweep() -> Callable[..., list[str]]:
    """
    Fail each PyMem allocation of a call in turn and name what each failure produced.

    A count-only run (position 0) measures the call's allocations, then runs 1..N each fail one of them, the failure
    libxml2's fuzzers inject at one chosen position (``xmlFuzzInjectFailure`` in its ``fuzz/fuzz.c``). Each entry is
    the escaping exception's name or ``result``, with a suffix when the injected failure never fired. ``setup`` builds
    a fresh argument for each run outside the injection window, so a cache the first run fills cannot shift later
    positions.
    """
    if "_fuzz_inject_failure" not in _HOOKS:
        pytest.fail("tests/fuzz_build needs the fuzz-only build: meson setup -Dfuzzing=true")
    inject: Final[Callable[[int], tuple[int, bool]]] = _HOOKS["_fuzz_inject_failure"]

    def sweep(call: Callable[[object], object], setup: Callable[[], object] = lambda: None) -> list[str]:
        argument = setup()
        inject(0)
        call(argument)
        allocations, _ = inject(0)
        outcomes = []
        for position in range(1, allocations + 1):
            argument = setup()
            inject(position)
            try:
                try:
                    call(argument)
                finally:
                    _, failed = inject(0)
            except Exception as exc:  # ruff: ignore[blind-except] - the outcome under test is which exception escapes
                outcome = type(exc).__name__
            else:
                outcome = "result"
            outcomes.append(outcome if failed else f"{outcome} without the injected failure")
        return outcomes

    return sweep
