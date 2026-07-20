"""
Keep every non-comparability note attached to a column that exists.

A note is keyed by operation and by the party label a competitor module publishes. Get either wrong and nothing
fails: the note is simply never rendered, and the column goes on reading as a straight loss. These checks fail
instead, which is the only way a silent miss gets caught.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tools"))

from bench import operations  # ruff:ignore[module-import-not-at-top-of-file]
from bench.migration import discover_labels  # ruff:ignore[module-import-not-at-top-of-file]
from bench.notes import NOTES  # ruff:ignore[module-import-not-at-top-of-file]

_COMPETITORS = _ROOT / "tools" / "bench" / "competitors"
_PAIRS = [(operation, party) for operation, parties in NOTES.items() for party in parties]


@pytest.mark.parametrize("operation", sorted(NOTES), ids=sorted(NOTES))
def test_noted_operation_is_benchmarked(operation: str) -> None:
    assert operation in operations.OPERATIONS


@pytest.mark.parametrize(("operation", "party"), _PAIRS, ids=[f"{op}-{party}" for op, party in _PAIRS])
def test_noted_party_publishes_that_operation(operation: str, party: str) -> None:
    published = {
        label
        for op_labels in discover_labels(_COMPETITORS).values()
        for op, label in op_labels.items()
        if op == operation
    }
    assert party in published


@pytest.mark.parametrize(("operation", "party"), _PAIRS, ids=[f"{op}-{party}" for op, party in _PAIRS])
def test_note_says_what_differs(operation: str, party: str) -> None:
    # a note that only asserts incomparability tells a reader nothing they could check
    assert len(NOTES[operation][party]) > 40
