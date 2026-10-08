"""Lifecycle programs running in many threads at once.

The ThreadSanitizer job runs this module on free-threaded 3.14t under ``pytest --parallel-threads=auto``, so each
thread count multiplies the programs that contend on the module and interpreter state.
"""

from __future__ import annotations

from typing import Final

from fuzz.dom_lifecycle import dom_lifecycle_race, dom_lifecycle_seeds, run_dom_lifecycle


def test_dom_lifecycle_race_matches_the_serial_run() -> None:
    seeds: Final = dom_lifecycle_seeds()[::8]  # the seeds run each opcode over 8 slots
    assert dom_lifecycle_race(seeds) == [run_dom_lifecycle(bytes.fromhex(seed))[0] for seed in seeds]
