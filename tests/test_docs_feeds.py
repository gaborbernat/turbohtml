"""
Keep the performance guide's tables and the generator that writes them naming the same files.

:mod:`bench.report` emits one feed per operation, while ``docs/development/performance.rst`` names its tables for the
section they sit in, so :data:`bench.docs_feeds.TABLES` is the only thing tying the two together. When the guide gained
a table that the map did not know about, refreshing it meant copying files across by hand, and the committed feeds
drifted until they carried stale numbers and had lost competitor columns. These checks fail the moment the two sides
disagree again.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tools"))

from bench.docs_feeds import TABLES, Combined, merge_party_feeds  # ruff:ignore[module-import-not-at-top-of-file]
from bench.operations import OPERATIONS  # ruff:ignore[module-import-not-at-top-of-file]

_GUIDE = _ROOT / "docs" / "development" / "performance.rst"
_REFERENCED = sorted(set(re.findall(r"bench/([\w-]+)\.json", _GUIDE.read_text(encoding="utf-8"))))


def _operations(table: str | Combined) -> tuple[str, ...]:
    """Return every operation a table draws a cell from."""
    if isinstance(table, str):
        return (table,)
    return tuple(operation for _, operation in table.rows) + tuple(operation for operation, _ in table.columns.values())


@pytest.mark.parametrize("name", [pytest.param(name, id=name) for name in _REFERENCED])
def test_guide_table_has_a_generator_entry(name: str) -> None:
    """Every table the guide renders is one the generator knows how to write."""
    assert name in TABLES


@pytest.mark.parametrize("name", [pytest.param(name, id=name) for name in sorted(TABLES)])
def test_generator_entry_is_rendered_by_the_guide(name: str) -> None:
    """The generator writes no feed the guide has stopped referencing."""
    assert name in _REFERENCED


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(operation, id=f"{name}-{operation}")
        for name, table in sorted(TABLES.items())
        for operation in _operations(table)
    ],
)
def test_generator_entry_names_a_real_operation(operation: str) -> None:
    """A table cannot source a cell from an operation the bench no longer runs."""
    assert operation in OPERATIONS


def test_merge_party_feeds_preserves_existing_columns(tmp_path: Path) -> None:
    feeds = tmp_path / "feeds"
    output = tmp_path / "output"
    feeds.mkdir()
    output.mkdir()
    source = {
        "label": "parse",
        "parties": ["turbohtml", "JustHTML"],
        "metrics": [],
        "rows": [["small", 1.0, 4.0]],
        "spread": [[None, 0.01, 0.04]],
        "notes": {"JustHTML": "raw parser"},
    }
    target = {
        "label": "parse",
        "parties": ["turbohtml", "lxml"],
        "metrics": [],
        "rows": [["small", 2.0, 3.0]],
        "spread": [[None, 0.02, 0.03]],
        "notes": {},
    }
    (feeds / "parse.json").write_text(json.dumps(source), encoding="utf-8")
    (output / "parsing.json").write_text(json.dumps(target), encoding="utf-8")

    assert merge_party_feeds(feeds, output, "JustHTML") == []
    assert json.loads((output / "parsing.json").read_text(encoding="utf-8")) == {
        "label": "parse",
        "parties": ["turbohtml", "lxml", "JustHTML"],
        "metrics": [],
        "rows": [["small", 2.0, 3.0, 4.0]],
        "spread": [[None, 0.02, 0.03, 0.04]],
        "notes": {"JustHTML": "raw parser"},
    }


def test_merge_party_feeds_extends_combined_table(tmp_path: Path) -> None:
    feeds = tmp_path / "feeds"
    output = tmp_path / "output"
    feeds.mkdir()
    output.mkdir()
    table = TABLES["markdown"]
    assert isinstance(table, Combined)
    cases = [case for case, _operation in table.rows]
    source = {
        "label": "markdown",
        "parties": ["turbohtml", "JustHTML"],
        "metrics": [],
        "rows": [[case, float(index), float(index + 10)] for index, case in enumerate(cases[:-2])],
        "spread": [[None, 0.01, 0.02] for _case in cases[:-2]],
        "notes": {},
    }
    target = {
        "label": "HTML to Markdown",
        "parties": ["turbohtml", "markdownify", "html2text"],
        "metrics": [],
        "rows": [[case, 1.0, 2.0, 3.0] for case in cases],
        "spread": [[None, 0.1, 0.2, 0.3] for _case in cases],
        "notes": {},
    }
    (feeds / "markdown.json").write_text(json.dumps(source), encoding="utf-8")
    (output / "markdown.json").write_text(json.dumps(target), encoding="utf-8")

    assert merge_party_feeds(feeds, output, "JustHTML") == []
    merged = json.loads((output / "markdown.json").read_text(encoding="utf-8"))
    assert merged["parties"] == ["turbohtml", "markdownify", "html2text", "JustHTML"]
    assert [row[-1] for row in merged["rows"]] == [
        10.0,
        11.0,
        12.0,
        "no equivalent operation",
        "no equivalent operation",
    ]
    assert [row[-1] for row in merged["spread"]] == [0.02, 0.02, 0.02, None, None]


def test_merge_party_feeds_reports_missing_combined_target(tmp_path: Path) -> None:
    feeds = tmp_path / "feeds"
    feeds.mkdir()
    (feeds / "markdown.json").write_text(
        json.dumps({
            "label": "markdown",
            "parties": ["turbohtml", "JustHTML"],
            "metrics": [],
            "rows": [],
            "notes": {},
        }),
        encoding="utf-8",
    )

    assert merge_party_feeds(feeds, tmp_path / "output", "JustHTML") == ["markdown"]
