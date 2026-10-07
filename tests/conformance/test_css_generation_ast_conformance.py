"""Native stylesheet rules omit at-rules, so budget checks need the complete reference tree."""

from __future__ import annotations

import json
import random
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # Node hosts the pinned independent CSS parser.
from pathlib import Path
from typing import Final, cast

import pytest
from fuzz.css_structure_generators import css_generate, css_grammar
from fuzz.structure_generators import Generated, GenerationBudget, generate, generation_sweep

_GRAMMAR: Final = css_grammar()
_SWEEP: Final = generation_sweep(_GRAMMAR, budget=GenerationBudget(512, 128))
_CASES: Final = (
    *_SWEEP,
    *(css_generate(random.Random(seed)) for seed in range(64)),
    *(css_generate(random.Random(seed), 64, steps=12) for seed in range(32)),
    *(
        generate(css_grammar(()), random.Random(0), GenerationBudget(128, 64), force=name)
        for name in (
            "css:leaf",
            "css:siblings",
            "css:nested:media",
            "css:nested:supports",
            "css:nested:container",
            "css:nested:layer",
        )
    ),
)
_NODE: Final = shutil.which("node") or "node"
_AST: Final = Path(__file__).resolve().parents[2] / "tools" / "bench" / "node" / "node_modules" / "css-tree"


@pytest.fixture(scope="module")
def css_metrics() -> dict[bytes, tuple[int, int]]:
    script: Final = """
const tree = require(process.argv[1]);
const fs = require('node:fs');
if (require(process.argv[1] + '/package.json').version !== '3.2.1') throw new Error('CSS AST version');
const rows = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(rows.map(source => {
    let count = 0;
    let level = -1;
    let height = 0;
    tree.walk(tree.parse(source, {parseCustomProperty: true}), {
        enter() { count++; level++; height = Math.max(height, level); },
        leave() { level--; }
    });
    return [count, height];
})));
"""
    result: Final = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]  # Fixed parser program; source bytes use stdin.
        (_NODE, "-e", script, str(_AST)),
        input=json.dumps([case.data.decode("utf-8") for case in _CASES]),
        capture_output=True,
        check=True,
        text=True,
    )
    return {
        case.data: (metric[0], metric[1])
        for case, metric in zip(_CASES, cast("list[list[int]]", json.loads(result.stdout)), strict=True)
    }


@pytest.mark.parametrize("case", _CASES, ids=[f"css-{index}" for index in range(len(_CASES))])
def test_css_complete_ast_budget(case: Generated, css_metrics: dict[bytes, tuple[int, int]]) -> None:
    assert css_metrics[case.data] == (case.nodes, case.depth)
