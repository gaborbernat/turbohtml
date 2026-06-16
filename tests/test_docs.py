"""Every ``>>>`` example in the prose docs must run and match its shown output."""

from __future__ import annotations

import doctest
from pathlib import Path

import pytest

_DOCS = Path(__file__).resolve().parent.parent / "docs"


@pytest.mark.parametrize("page", ["migration.rst", "how-to.rst", "tutorials.rst"])
def test_doc_examples_run(page: str) -> None:
    results = doctest.testfile(str(_DOCS / page), module_relative=False, verbose=False)
    assert results.failed == 0
