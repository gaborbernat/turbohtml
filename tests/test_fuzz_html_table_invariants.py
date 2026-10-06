from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final, cast

import pytest
from fuzz.html_table_oracles import (
    UnsupportedHtmlTableCaseError,
    html_table_check,
    html_table_controls,
    html_table_generate,
    html_table_seeds,
)
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main

from turbohtml import Element, Text, parse_fragment

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("case", "source", "expected"),
    [
        pytest.param(
            "td:implied:1:plain",
            '<table id="z"><tr id="x"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr></table>',
            [
                ("table", "z", 0),
                ("tbody", "", 1),
                ("tr", "x", 2),
                ("td", "x", 3),
                ("#text", "MiXeD", 4),
                ("td", "y", 3),
                ("#text", "MiXeD", 6),
            ],
            id="inserted-row-group",
        ),
        pytest.param(
            "th:explicit:1:numeric",
            '<table id="z"><tbody><tr id="x"><th id="x">&#65;&#x42;&#67;</th>'
            '<th id="y">&#65;&#x42;&#67;</th></tr></tbody></table>',
            [
                ("table", "z", 0),
                ("tbody", "", 1),
                ("tr", "x", 2),
                ("th", "x", 3),
                ("#text", "ABC", 4),
                ("th", "y", 3),
                ("#text", "ABC", 6),
            ],
            id="explicit-numeric-cells",
        ),
        pytest.param(
            "td:explicit:2:named",
            '<table id="z"><tbody><tr id="x"><td id="x">&amp;&lt;&gt;</td><td id="y">&amp;&lt;&gt;</td></tr>'
            '<tr id="y"><td id="x">&amp;&lt;&gt;</td><td id="y">&amp;&lt;&gt;</td></tr></tbody></table>',
            [
                ("table", "z", 0),
                ("tbody", "", 1),
                ("tr", "x", 2),
                ("td", "x", 3),
                ("#text", "&<>", 4),
                ("td", "y", 3),
                ("#text", "&<>", 6),
                ("tr", "y", 2),
                ("td", "x", 8),
                ("#text", "&<>", 9),
                ("td", "y", 8),
                ("#text", "&<>", 11),
            ],
            id="explicit-two-rows-named",
        ),
        pytest.param(
            "th:implied:2:plain",
            '<table id="z"><tr id="x"><th id="x">MiXeD</th><th id="y">MiXeD</th></tr>'
            '<tr id="y"><th id="x">MiXeD</th><th id="y">MiXeD</th></tr></table>',
            [
                ("table", "z", 0),
                ("tbody", "", 1),
                ("tr", "x", 2),
                ("th", "x", 3),
                ("#text", "MiXeD", 4),
                ("th", "y", 3),
                ("#text", "MiXeD", 6),
                ("tr", "y", 2),
                ("th", "x", 8),
                ("#text", "MiXeD", 9),
                ("th", "y", 8),
                ("#text", "MiXeD", 11),
            ],
            id="inserted-group-two-rows",
        ),
    ],
)
def test_html_table_literal_trees(case: str, source: str, expected: list[tuple[str, str, int]]) -> None:
    root: Final = parse_fragment(source)
    nodes: Final = [root, *root.descendants]
    assert (
        [
            (
                node.tag if isinstance(node, Element) else "#text",
                cast("str", node.attrs.get("id", "")) if isinstance(node, Element) else cast("Text", node).data,
                nodes.index(cast("Element", node.parent)),
            )
            for node in nodes[1:]
        ],
        {node.namespace.value for node in root.iter_elements()},
        html_table_check(case),
        html_table_check(case, lambda _node: source),
        html_table_check(case, lambda _node: ""),
    ) == (expected, {"html"}, None, None, "serialized table tree differs from literals")


def test_html_table_checks_first_parse() -> None:
    source: Final = '<table id="z"><thead><tr id="x"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr></thead></table>'
    assert (
        html_table_check("td:implied:1:plain", read=lambda _source: parse_fragment(source))
        == "parsed table tree differs from literals"
    )


def test_html_table_checks_repeat_formatting() -> None:
    source: Final = '<table id="z"><tbody><tr id="x"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr></tbody></table>'
    outputs: Final = iter([source, source.replace('"', "'")])
    assert (
        html_table_check("td:implied:1:plain", lambda _node: next(outputs)) == "table serialization changes on repeat"
    )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            '<table id="z"><thead><tr id="x"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr>'
            '<tr id="y"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr></thead></table>',
            id="changed-row-group",
        ),
        pytest.param(
            '<table id="z"><tbody id="x"><tr id="x"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr>'
            '<tr id="y"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr></tbody></table>',
            id="unexpected-group-attribute",
        ),
        pytest.param(
            '<table id="z"><tbody><tr id="x"><td id="x">MiXeD</td></tr>'
            '<tr id="y"><td id="y">MiXeD</td><td id="x">MiXeD</td><td id="y">MiXeD</td></tr></tbody></table>',
            id="cell-moved-to-following-row",
        ),
        pytest.param(
            '<table id="z"><tbody><tr id="x"><th id="x">MiXeD</th><th id="y">MiXeD</th></tr>'
            '<tr id="y"><th id="x">MiXeD</th><th id="y">MiXeD</th></tr></tbody></table>',
            id="changed-cell-type",
        ),
        pytest.param(
            '<table id="z"><tbody><tr id="x"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr></tbody></table>',
            id="dropped-row",
        ),
        pytest.param(
            '<table id="z"><tbody><tr id="x"><td id="x">WRONG</td><td id="y">MiXeD</td></tr>'
            '<tr id="y"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr></tbody></table>',
            id="changed-text",
        ),
        pytest.param(
            '<table id="z"><tbody><tr id="x"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr>'
            '<tr id="y"><td id="x">MiXeD</td><td id="x">MiXeD</td></tr></tbody></table>',
            id="changed-cell-id",
        ),
        pytest.param("<!--unexpected-->", id="unexpected-comment"),
        pytest.param("", id="lost-tree"),
    ],
)
def test_html_table_rejects_changed_tree(source: str) -> None:
    assert (
        html_table_check("td:explicit:2:plain", lambda _node: source) == "serialized table tree differs from literals"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("", id="missing-program"),
        pytest.param("div:explicit:1:plain", id="cell-pool"),
        pytest.param("td:raw:1:plain", id="group-pool"),
        pytest.param("td:explicit:0:plain", id="empty-table"),
        pytest.param("td:explicit:3:plain", id="row-budget"),
        pytest.param("td:explicit:1:raw", id="terminal-pool"),
    ],
)
def test_html_table_rejects_unsupported_grammar(case: str) -> None:
    with pytest.raises(UnsupportedHtmlTableCaseError):
        html_table_check(case)
    with pytest.raises(OutOfScopeError):
        ORACLES["html-table-grammar"].check(case)


def test_html_table_production_sweep_and_bounds() -> None:
    seeds: Final = html_table_seeds()
    rng: Final = random.Random(1018)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - Reproducible grammar samples.
    generated: Final = [html_table_generate(rng) for _ in range(100)]
    assert (
        len(seeds),
        len(set(seeds)),
        Counter(case.split(":")[0] for case in seeds),
        Counter(case.split(":")[1] for case in seeds),
        Counter(case.split(":")[2] for case in seeds),
        Counter(case.split(":")[3] for case in seeds),
        set(generated) <= set(seeds),
        all(html_table_check(case) is None for case in [*seeds, *generated]),
        html_table_controls(),
    ) == (
        24,
        24,
        {"td": 12, "th": 12},
        {"explicit": 12, "implied": 12},
        {"1": 12, "2": 12},
        {"plain": 8, "named": 8, "numeric": 8},
        True,
        True,
        {"changed row group": True, "dropped row": True, "encoded text": True},
    )


def test_html_table_generated_trees_obey_bounds() -> None:
    bounds: Final[set[tuple[int, int, int]]] = set()
    identifiers: Final[set[str]] = set()

    def capture(source: str) -> Element:
        root: Final = parse_fragment(source)
        elements: Final = [node for node in root.descendants if isinstance(node, Element)]
        bounds.add((
            len(elements),
            sum(isinstance(node, Text) for node in root.descendants),
            max(sum(isinstance(ancestor, Element) for ancestor in element.ancestors) for element in elements),
        ))
        identifiers.update(
            cast("str", identifier) for element in elements if (identifier := element.attrs.get("id")) is not None
        )
        return root

    assert (all(html_table_check(case, read=capture) is None for case in html_table_seeds()), bounds, identifiers) == (
        True,
        {(5, 2, 4), (8, 4, 4)},
        {"x", "y", "z"},
    )


def test_html_table_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "html-table-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "24" in capsys.readouterr().out) == (0, [], True)


def test_html_table_cli_emits_group_change(mocker: MockerFixture, tmp_path: Path) -> None:
    source: Final = '<table id="z"><thead><tr id="x"><td id="x">MiXeD</td><td id="y">MiXeD</td></tr></thead></table>'
    oracle: Final = replace(
        ORACLES["html-table-grammar"],
        check=partial(html_table_check, serialize=lambda _node: source),
        seeds=lambda: ["td:implied:1:plain"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"html-table-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "html-table-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (
        1,
        1,
        "serialized table tree differs from literals",
        1,
    )


def test_html_table_cli_rejection_is_out_of_scope(
    mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oracle: Final = replace(ORACLES["html-table-grammar"], seeds=lambda: ["invalid"], floor=Floor(1, 1))
    mocker.patch.dict(ORACLES, {"html-table-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "html-table-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("*.json")), "VACUOUS RUN" in capsys.readouterr().err) == (2, [], True)
