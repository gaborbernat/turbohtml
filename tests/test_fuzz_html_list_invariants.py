from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final, cast

import pytest
from fuzz.html_list_oracles import (
    UnsupportedHtmlListCaseError,
    html_list_check,
    html_list_controls,
    html_list_generate,
    html_list_seeds,
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
            "ul:flat:explicit:plain",
            '<ul id="z"><li id="x">MiXeD</li><li id="y">MiXeD</li></ul>',
            [("ul", "z", 0), ("li", "x", 1), ("#text", "MiXeD", 2), ("li", "y", 1), ("#text", "MiXeD", 4)],
            id="flat-explicit",
        ),
        pytest.param(
            "ol:flat:implied:numeric",
            '<ol id="z"><li id="x">&#65;&#x42;&#67;<li id="y">&#65;&#x42;&#67;</ol>',
            [("ol", "z", 0), ("li", "x", 1), ("#text", "ABC", 2), ("li", "y", 1), ("#text", "ABC", 4)],
            id="flat-implied-numeric",
        ),
        pytest.param(
            "ul:nested:explicit:named",
            '<ul id="z"><li id="x">&amp;&lt;&gt;<ul id="z"><li id="x">&amp;&lt;&gt;</li>'
            '<li id="y">&amp;&lt;&gt;</li></ul></li><li id="y">&amp;&lt;&gt;</li></ul>',
            [
                ("ul", "z", 0),
                ("li", "x", 1),
                ("#text", "&<>", 2),
                ("ul", "z", 2),
                ("li", "x", 4),
                ("#text", "&<>", 5),
                ("li", "y", 4),
                ("#text", "&<>", 7),
                ("li", "y", 1),
                ("#text", "&<>", 9),
            ],
            id="nested-explicit-named",
        ),
        pytest.param(
            "ol:nested:implied:plain",
            '<ol id="z"><li id="x">MiXeD<ol id="z"><li id="x">MiXeD<li id="y">MiXeD</ol><li id="y">MiXeD</ol>',
            [
                ("ol", "z", 0),
                ("li", "x", 1),
                ("#text", "MiXeD", 2),
                ("ol", "z", 2),
                ("li", "x", 4),
                ("#text", "MiXeD", 5),
                ("li", "y", 4),
                ("#text", "MiXeD", 7),
                ("li", "y", 1),
                ("#text", "MiXeD", 9),
            ],
            id="nested-implied",
        ),
    ],
)
def test_html_list_literal_trees(case: str, source: str, expected: list[tuple[str, str, int]]) -> None:
    root: Final = parse_fragment(source)
    nodes: Final = [root, *root.descendants]
    assert (
        [
            (
                node.tag if isinstance(node, Element) else "#text",
                node.attrs["id"] if isinstance(node, Element) else cast("Text", node).data,
                nodes.index(cast("Element", node.parent)),
            )
            for node in nodes[1:]
        ],
        {node.namespace.value for node in root.iter_elements()},
        html_list_check(case),
        html_list_check(case, lambda _node: source),
        html_list_check(case, lambda _node: ""),
    ) == (expected, {"html"}, None, None, "serialized list tree differs from literals")


def test_html_list_checks_first_parse() -> None:
    assert (
        html_list_check("ul:nested:implied:plain", read=lambda _source: parse_fragment("<ul></ul>"))
        == "parsed list tree differs from literals"
    )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            '<ul id="z"><li id="x">MiXeD<ul id="z"><li id="x">MiXeD</li></ul></li>'
            '<li id="y">MiXeD</li><li id="y">MiXeD</li></ul>',
            id="inner-item-moved-to-outer-list",
        ),
        pytest.param(
            '<ul id="z"><li id="x">MiXeD<ul id="z"><li id="x">MiXeD</li>'
            '<li id="y">MiXeD</li><li id="y">MiXeD</li></ul></li></ul>',
            id="outer-item-moved-to-inner-list",
        ),
        pytest.param('<ul id="z"><li id="x">MiXeD</li></ul>', id="lost-nested-siblings"),
        pytest.param(
            '<ul id="z"><li id="x">WRONG<ul id="z"><li id="x">MiXeD</li>'
            '<li id="y">MiXeD</li></ul></li><li id="y">MiXeD</li></ul>',
            id="changed-text",
        ),
        pytest.param(
            '<ul id="z"><li id="x">MiXeD<ul id="z"><li id="x">MiXeD</li>'
            '<li id="y">MiXeD</li></ul></li><li id="x">MiXeD</li></ul>',
            id="changed-id",
        ),
        pytest.param('<svg><ul id="z"></ul></svg>', id="changed-namespace"),
        pytest.param("<!--unexpected-->", id="unexpected-comment"),
        pytest.param("", id="lost-tree"),
    ],
)
def test_html_list_rejects_changed_tree(source: str) -> None:
    assert (
        html_list_check("ul:nested:explicit:plain", lambda _node: source)
        == "serialized list tree differs from literals"
    )


def test_html_list_checks_repeat_formatting() -> None:
    source: Final = '<ul id="z"><li id="x">MiXeD</li><li id="y">MiXeD</li></ul>'
    outputs: Final = iter([source, source.replace('"', "'")])
    assert (
        html_list_check("ul:flat:explicit:plain", lambda _node: next(outputs)) == "list serialization changes on repeat"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("", id="missing-program"),
        pytest.param("menu:flat:explicit:plain", id="tag-pool"),
        pytest.param("ul:deep:explicit:plain", id="depth-bound"),
        pytest.param("ul:flat:missing:plain", id="ending-pool"),
        pytest.param("ul:flat:explicit:raw", id="terminal-pool"),
        pytest.param("ul:flat:explicit:plain:extra", id="trailing-program"),
    ],
)
def test_html_list_rejects_unsupported_grammar(case: str) -> None:
    with pytest.raises(UnsupportedHtmlListCaseError):
        html_list_check(case)
    with pytest.raises(OutOfScopeError):
        ORACLES["html-list-grammar"].check(case)


def test_html_list_production_sweep_and_bounds() -> None:
    seeds: Final = html_list_seeds()
    rng: Final = random.Random(1018)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - Reproducible grammar samples.
    generated: Final = [html_list_generate(rng) for _ in range(100)]
    assert (
        len(seeds),
        len(set(seeds)),
        Counter(case.split(":")[0] for case in seeds),
        Counter(case.split(":")[1] for case in seeds),
        Counter(case.split(":")[2] for case in seeds),
        Counter(case.split(":")[3] for case in seeds),
        set(generated) <= set(seeds),
        all(html_list_check(case) is None for case in [*seeds, *generated]),
        html_list_controls(),
    ) == (
        24,
        24,
        {"ul": 12, "ol": 12},
        {"flat": 12, "nested": 12},
        {"explicit": 12, "implied": 12},
        {"plain": 8, "named": 8, "numeric": 8},
        True,
        True,
        {"inner item became outer sibling": True, "dropped sibling": True, "encoded text": True},
    )


def test_html_list_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "html-list-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "24" in capsys.readouterr().out) == (0, [], True)


def test_html_list_cli_emits_attachment_loss(mocker: MockerFixture, tmp_path: Path) -> None:
    source: Final = (
        '<ul id="z"><li id="x">MiXeD<ul id="z"><li id="x">MiXeD</li></ul></li>'
        '<li id="y">MiXeD</li><li id="y">MiXeD</li></ul>'
    )
    oracle: Final = replace(
        ORACLES["html-list-grammar"],
        check=partial(html_list_check, serialize=lambda _node: source),
        seeds=lambda: ["ul:nested:explicit:plain"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"html-list-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "html-list-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (
        1,
        1,
        "serialized list tree differs from literals",
        1,
    )


def test_html_list_cli_rejection_is_out_of_scope(
    mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oracle: Final = replace(ORACLES["html-list-grammar"], seeds=lambda: ["invalid"], floor=Floor(1, 1))
    mocker.patch.dict(ORACLES, {"html-list-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "html-list-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("*.json")), "VACUOUS RUN" in capsys.readouterr().err) == (2, [], True)


def test_html_list_generated_trees_obey_bounds() -> None:
    bounds: Final[set[tuple[int, int, int]]] = set()
    identifiers: Final[set[str]] = set()

    def capture(source: str) -> Element:
        root: Final = parse_fragment(source)
        elements: Final = [node for node in root.iter_elements() if node is not root]
        depths: Final[list[int]] = []
        for element in elements:
            depth = 0
            parent = element
            while parent is not root:
                depth += 1
                parent = cast("Element", parent.parent)
            depths.append(depth)
        bounds.add((len(elements), sum(isinstance(node, Text) for node in root.descendants), max(depths)))
        identifiers.update(cast("str", element.attrs["id"]) for element in elements)
        return root

    assert (all(html_list_check(case, read=capture) is None for case in html_list_seeds()), bounds, identifiers) == (
        True,
        {(3, 2, 2), (6, 4, 4)},
        {"x", "y", "z"},
    )
