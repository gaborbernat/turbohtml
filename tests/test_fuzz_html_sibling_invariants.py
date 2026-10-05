from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.html_grammar_oracles import (
    UnsupportedHtmlSiblingCaseError,
    html_sibling_check,
    html_sibling_controls,
    html_sibling_generate,
    html_sibling_seeds,
)
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main

from turbohtml import parse_fragment

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("case", "source", "expected"),
    [
        pytest.param(
            "span:title:bare:2:empty",
            "<span title=Token></span>" * 2,
            [("span", {"title": "Token"}, "")] * 2,
            id="identical-empty-siblings",
        ),
        pytest.param(
            "em:data-x:single:1:plain",
            "<em data-x='Token'>MiXeD</em>",
            [("em", {"data-x": "Token"}, "MiXeD")],
            id="single-quote",
        ),
        pytest.param(
            "code:title:double:1:named",
            '<code title="&quot;&apos;&amp;">&amp;&lt;&gt;</code>',
            [("code", {"title": "\"'&"}, "&<>")],
            id="named-references",
        ),
        pytest.param(
            "span:data-x:bare:1:numeric",
            "<span data-x=&#x26;&#34;>&#65;&#x42;&#67;</span>",
            [("span", {"data-x": '&"'}, "ABC")],
            id="numeric-references",
        ),
    ],
)
def test_html_sibling_literal_trees(case: str, source: str, expected: list[tuple[str, dict[str, str], str]]) -> None:
    root: Final = parse_fragment(source)
    assert (
        [(node.tag, dict(node.attrs), node.text) for node in root.iter_elements() if node is not root],
        html_sibling_check(case),
        html_sibling_check(case, lambda _node: source[: len(source) // int(case.split(":")[3])]),
        html_sibling_check(case, lambda _node: ""),
    ) == (expected, None, None, "serialized sibling tree differs from literals")


def test_html_sibling_checks_the_first_parse() -> None:
    assert html_sibling_check("span:title:bare:2:empty", read=lambda _text: parse_fragment("<span></span>")) == (
        "parsed sibling tree differs from literals"
    )


def test_html_sibling_rejects_unexpected_comment() -> None:
    assert html_sibling_check("span:title:bare:1:empty", lambda _node: "<!--unexpected-->") == (
        "serialized sibling tree differs from literals"
    )


def test_html_sibling_checks_repeat_formatting() -> None:
    outputs: Final = iter(['<span title="Token"></span>', "<span title='Token'></span>"])
    assert html_sibling_check("span:title:bare:1:empty", lambda _node: next(outputs)) == (
        "sibling serialization changes on repeat"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("", id="missing-program"),
        pytest.param("div:title:bare:1:empty", id="tag-pool"),
        pytest.param("span:href:bare:1:empty", id="attribute-pool"),
        pytest.param("span:title:raw:1:empty", id="quote-pool"),
        pytest.param("span:title:bare:0:empty", id="zero-siblings"),
        pytest.param("span:title:bare:5:empty", id="node-budget"),
        pytest.param("span:title:bare:1:raw", id="terminal-pool"),
    ],
)
def test_html_sibling_rejects_unsupported_grammar(case: str) -> None:
    with pytest.raises(UnsupportedHtmlSiblingCaseError):
        html_sibling_check(case)
    with pytest.raises(OutOfScopeError):
        ORACLES["html-sibling-grammar"].check(case)


def test_html_sibling_production_sweep_and_bounds() -> None:
    seeds: Final = html_sibling_seeds()
    rng: Final = random.Random(1018)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - Reproducible grammar samples.
    generated: Final = [html_sibling_generate(rng) for _ in range(100)]
    leaves: Final = Counter(case.rsplit(":", 1)[1] for case in seeds)
    assert (
        len(seeds),
        leaves,
        all(html_sibling_check(case) is None for case in [*seeds, *generated]),
        max(int(case.split(":")[3]) for case in [*seeds, *generated]),
        html_sibling_controls(),
    ) == (
        288,
        {"empty": 72, "plain": 72, "named": 72, "numeric": 72},
        True,
        4,
        {"dropped identical sibling": True, "changed attribute": True, "encoded text": True},
    )


def test_html_sibling_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "html-sibling-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "288" in capsys.readouterr().out) == (0, [], True)


def test_html_sibling_cli_emits_multiplicity_loss(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["html-sibling-grammar"],
        check=partial(html_sibling_check, serialize=lambda _node: ""),
        seeds=lambda: ["span:title:bare:2:empty"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"html-sibling-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "html-sibling-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (
        1,
        1,
        "serialized sibling tree differs from literals",
        1,
    )


def test_html_sibling_cli_rejection_is_out_of_scope(
    mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oracle: Final = replace(ORACLES["html-sibling-grammar"], seeds=lambda: ["invalid"], floor=Floor(1, 1))
    mocker.patch.dict(ORACLES, {"html-sibling-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "html-sibling-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("*.json")), "VACUOUS RUN" in capsys.readouterr().err) == (2, [], True)
