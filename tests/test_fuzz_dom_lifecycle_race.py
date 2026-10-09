"""Lifecycle programs running in many threads at once.

The ThreadSanitizer job runs this module on free-threaded 3.14t under ``pytest --parallel-threads=auto``, so each
thread count multiplies the programs that contend on the module and interpreter state.
"""

from __future__ import annotations

from typing import Final

from fuzz.dom_lifecycle import dom_lifecycle_race, dom_lifecycle_seeds, run_dom_lifecycle

_SEEDS: Final = dom_lifecycle_seeds()[::8]  # the seeds run each opcode over 8 slots


def test_dom_lifecycle_race_matches_the_serial_run() -> None:
    assert dom_lifecycle_race(_SEEDS) == [run_dom_lifecycle(bytes.fromhex(seed))[0] for seed in _SEEDS]


def test_dom_lifecycle_race_on_shared_trees_keeps_every_tree_intact() -> None:
    traces: Final = dom_lifecycle_race(_SEEDS, shared=True)
    assert {step.violations for trace in traces for step in trace} == {(0, 0, 0, 0)}
