from __future__ import annotations

import hashlib
import json
import random
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # Node hosts the pinned independent CSS parser.
from pathlib import Path
from typing import Final, cast

import pytest
from fuzz.css_generation_tables import CSS_ROWS
from fuzz.css_structure_generators import css_generate, css_grammar, css_source_generate, css_source_seeds, main
from fuzz.structure_generators import (
    BudgetError,
    Generated,
    GenerationBudget,
    Grammar,
    ProductionFloorError,
    assert_production_floors,
    generate,
    generation_sweep,
)

from turbohtml.cssom import StyleSheet

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
_AST: Final = Path(__file__).resolve().parents[1] / "tools" / "bench" / "node" / "node_modules" / "css-tree"
_AST_AVAILABLE: Final = shutil.which(_NODE) is not None and _AST.is_dir()
_PREFIX: Final = b":root{--x:red;--y:red;--z:red;--u:red;}@keyframes v{from{opacity:0}}"
_BINDINGS: Final = (("anim", "v"), ("cssvara", "x"), ("cssvarb", "y"), ("cssvarc", "z"), ("cssvard", "u"))


@pytest.fixture
def literal_grammar() -> Grammar:
    return css_grammar(())


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


@pytest.mark.skipif(not _AST_AVAILABLE, reason="requires pinned css-tree reference")
@pytest.mark.parametrize("case", _CASES, ids=[f"css-{index}" for index in range(len(_CASES))])
def test_css_complete_ast_budget(case: Generated, css_metrics: dict[bytes, tuple[int, int]]) -> None:
    assert css_metrics[case.data] == (case.nodes, case.depth)


def test_css_complete_pinned_inventory() -> None:
    assert (
        len(CSS_ROWS),
        sum(row[0] == "css.txt" for row in CSS_ROWS),
        sum(row[0] == "cssproperties.txt" for row in CSS_ROWS),
        sum(row[0] == "blink-css.dict" for row in CSS_ROWS),
        sum(bool(row[9]) for row in CSS_ROWS),
        sum(row[10] for row in CSS_ROWS),
    ) == (6349, 1567, 3294, 1488, 332, 3)


def test_css_complete_production_floor() -> None:
    assert set(assert_production_floors(_SWEEP, (production.name for production in _GRAMMAR.productions))) == {
        production.name for production in _GRAMMAR.productions
    }


def test_css_complete_unknown_production_fails_floor() -> None:
    with pytest.raises(ProductionFloorError, match="floors missed"):
        assert_production_floors(_SWEEP, ("css:disabled",))


@pytest.mark.parametrize(
    ("name", "body", "nodes"),
    [
        pytest.param("css:leaf", b"a{color:red}", 38, id="rule"),
        pytest.param("css:siblings", b"a{color:red}a{color:red}", 46, id="siblings"),
        pytest.param("css:nested:media", b"@media all{a{color:red}}", 43, id="media"),
        pytest.param("css:nested:supports", b"@supports(display:grid){a{color:red}}", 46, id="supports"),
        pytest.param("css:nested:container", b"@container(width>1px){a{color:red}}", 45, id="container"),
        pytest.param("css:nested:layer", b"@layer x{a{color:red}}", 43, id="layer"),
    ],
)
def test_css_complete_literal_shapes(literal_grammar: Grammar, name: str, body: bytes, nodes: int) -> None:
    case: Final = generate(literal_grammar, random.Random(0), GenerationBudget(128, 64), force=name)
    assert (case.data, case.nodes, case.depth, case.bindings) == (_PREFIX + body, nodes, 7, _BINDINGS)


@pytest.mark.parametrize(
    "budget",
    [
        pytest.param(GenerationBudget(37, 64), id="nodes"),
        pytest.param(GenerationBudget(128, 1), id="steps"),
    ],
)
def test_css_complete_rejects_short_root_budget(literal_grammar: Grammar, budget: GenerationBudget) -> None:
    with pytest.raises(BudgetError, match="cannot complete"):
        generate(literal_grammar, random.Random(0), budget)


def test_css_complete_reserves_sibling_steps(literal_grammar: Grammar) -> None:
    with pytest.raises(BudgetError, match="cannot complete"):
        generate(literal_grammar, random.Random(0), GenerationBudget(128, 3), force="css:siblings")


@pytest.mark.parametrize(
    ("name", "body"),
    [
        pytest.param("css:domato:css.txt:107", b"a{color:var(--y)}", id="second-variable"),
        pytest.param("css:domato:cssproperties.txt:1080", b"a{border-image-outset:0 0px}", id="orphan-border"),
        pytest.param("css:domato:cssproperties.txt:1998", b"a{font-weight:0 0}", id="orphan-weight"),
        pytest.param("css:blink:959", b'@charset "UTF-8";', id="leading-charset"),
        pytest.param("css:blink:960", b"@import url(data:,x);", id="leading-import"),
        pytest.param("css:blink:961", b'@namespace svg "http://www.w3.org/2000/svg";', id="leading-namespace"),
    ],
)
def test_css_complete_literal_table_materialization(name: str, body: bytes) -> None:
    case: Final = generate(_GRAMMAR, random.Random(0), GenerationBudget(512, 128), force=name)
    assert case.data == (body + _PREFIX if name.startswith("css:blink:") else _PREFIX + body)


def test_css_complete_custom_properties_bind_to_root() -> None:
    case: Final = generate(_GRAMMAR, random.Random(0), GenerationBudget(512, 128), force="css:domato:css.txt:107")
    rules: Final = StyleSheet(case.data.decode("utf-8")).rules
    assert (rules[0].selector_text, rules[0].style.get("--y"), rules[1].style.get("color")) == (
        ":root",
        "red",
        "var(--y)",
    )


@pytest.mark.parametrize("seed", range(32))
def test_css_complete_random_inputs_respect_both_budgets(seed: int) -> None:
    case: Final = css_generate(random.Random(seed), 64, steps=12)
    assert case.nodes <= 64
    assert len(case.productions) <= 12


def test_css_complete_source_adapter() -> None:
    assert css_source_generate(random.Random(0)) == css_generate(random.Random(0)).data.decode("utf-8")


def test_css_complete_source_seeds_preserve_sweep() -> None:
    assert css_source_seeds() == [case.data.decode("utf-8") for case in _SWEEP]


def test_css_complete_cli_materializes_bytes(tmp_path: Path) -> None:
    case: Final = css_generate(random.Random(0), 64, steps=12)
    assert main(("--output", str(tmp_path), "--count", "1", "--budget", "64", "--steps", "12")) == 0
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {
        hashlib.sha256(case.data).hexdigest(): case.data
    }


def test_css_complete_cli_sweeps_productions(tmp_path: Path) -> None:
    assert main(("--output", str(tmp_path))) == 0
    assert {path.read_bytes() for path in tmp_path.iterdir()} == {case.data for case in _SWEEP}


@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        pytest.param("--count", "-1", "count must be nonnegative", id="count"),
        pytest.param("--budget", "0", "budget cannot complete", id="nodes"),
        pytest.param("--steps", "0", "budget cannot complete", id="steps"),
    ],
)
def test_css_complete_cli_rejects_invalid_budgets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], option: str, value: str, message: str
) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(("--output", str(tmp_path), "--count", "1", option, value))
    assert message in capsys.readouterr().err


def test_css_complete_disabled_alternative_fails_floor() -> None:
    name: Final = "css:domato:css.txt:107"
    with pytest.raises(ProductionFloorError, match=r"css:domato:css\.txt:107"):
        assert_production_floors((case for case in _SWEEP if name not in case.productions), (name,))
