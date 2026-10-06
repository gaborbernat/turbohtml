from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final, cast

import pytest
from fuzz.html_foreign_oracles import (
    UnsupportedHtmlForeignCaseError,
    html_foreign_check,
    html_foreign_controls,
    html_foreign_generate,
    html_foreign_seeds,
)
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main

from turbohtml import Element, parse_fragment

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("case", "source", "boundary", "decoded"),
    [
        pytest.param(
            "foreignObject:x:double:plain",
            '<svg><foreignObject><a id="x">MiXeD</a></foreignObject><g id="y"></g></svg>',
            "foreignObject",
            "MiXeD",
            id="foreign-object",
        ),
        pytest.param(
            "desc:y:single:named",
            "<svg><desc><a id='y'>&amp;&lt;&gt;</a></desc><g id='x'></g></svg>",
            "desc",
            "&<>",
            id="description",
        ),
        pytest.param(
            "title:x:double:numeric",
            '<svg><title><a id="x">&#65;&#x42;&#67;</a></title><g id="y"></g></svg>',
            "title",
            "ABC",
            id="title",
        ),
    ],
)
def test_html_foreign_literal_tree(case: str, source: str, boundary: str, decoded: str) -> None:
    root: Final = parse_fragment(source)
    assert (
        [
            (node.namespace.value, node.tag, cast("Element", node.parent).tag)
            for node in root.iter_elements()
            if node is not root
        ],
        next(root.iter_elements("a")).text,
        html_foreign_check(case),
        ORACLES["html-foreign-grammar"].check(case),
    ) == (
        [("svg", "svg", "div"), ("svg", boundary, "svg"), ("html", "a", boundary), ("svg", "g", "svg")],
        decoded,
        None,
        None,
    )


def test_html_foreign_first_parse() -> None:
    assert (
        html_foreign_check(
            "foreignObject:x:double:plain", read=lambda _text: parse_fragment("<svg><g><a>MiXeD</a></g></svg>")
        )
        == "parsed SVG integration tree differs from literals"
    )


@pytest.mark.parametrize(
    "serialized",
    [
        pytest.param('<svg><g><a id="x">MiXeD</a></g><g id="y"></g></svg>', id="namespace"),
        pytest.param('<svg><desc><a id="x">MiXeD</a><g id="y"></g></desc></svg>', id="parent"),
        pytest.param('<svg><desc><a id="y">MiXeD</a></desc><g id="y"></g></svg>', id="identifier"),
        pytest.param('<svg><desc><a id="x">changed</a></desc><g id="y"></g></svg>', id="text"),
        pytest.param("<!--unexpected-->", id="comment"),
        pytest.param("", id="empty"),
    ],
)
def test_html_foreign_serialized_corruption(serialized: str) -> None:
    assert html_foreign_check("desc:x:double:plain", lambda _node: serialized) == (
        "serialized SVG integration tree differs from literals"
    )


def test_html_foreign_repeat_formatting() -> None:
    outputs: Final = iter([
        '<svg><desc><a id="x">MiXeD</a></desc><g id="y"></g></svg>',
        "<svg><desc><a id='x'>MiXeD</a></desc><g id='y'></g></svg>",
    ])
    assert html_foreign_check("desc:x:double:plain", lambda _node: next(outputs)) == (
        "SVG integration serialization changes on repeat"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("", id="missing"),
        pytest.param("g:x:double:plain", id="boundary"),
        pytest.param("desc:z:double:plain", id="identifier"),
        pytest.param("desc:x:bare:plain", id="quote"),
        pytest.param("desc:x:double:raw", id="leaf"),
    ],
)
def test_html_foreign_unsupported_program(case: str) -> None:
    with pytest.raises(UnsupportedHtmlForeignCaseError):
        html_foreign_check(case)
    with pytest.raises(OutOfScopeError):
        ORACLES["html-foreign-grammar"].check(case)


def test_html_foreign_finite_productions() -> None:
    seeds: Final = html_foreign_seeds()
    rng: Final = random.Random(1018)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - Reproducible grammar samples.
    generated: Final = [html_foreign_generate(rng) for _ in range(100)]
    assert (
        len(seeds),
        Counter(case.split(":")[0] for case in seeds),
        Counter(case.rsplit(":", 1)[1] for case in seeds),
        set(generated) <= set(seeds),
        all(html_foreign_check(case) is None for case in [*seeds, *generated]),
        html_foreign_controls(),
    ) == (
        36,
        {"foreignObject": 12, "desc": 12, "title": 12},
        {"plain": 12, "named": 12, "numeric": 12},
        True,
        True,
        {
            "HTML child became SVG": True,
            "SVG sibling moved inside integration point": True,
            "changed identifier": True,
            "encoded text": True,
        },
    )


def test_html_foreign_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "html-foreign-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "36" in capsys.readouterr().out) == (0, [], True)


def test_html_foreign_cli_emits_loss(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["html-foreign-grammar"],
        check=partial(html_foreign_check, serialize=lambda _node: ""),
        seeds=lambda: ["desc:x:double:plain"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"html-foreign-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "html-foreign-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (
        1,
        1,
        "serialized SVG integration tree differs from literals",
        1,
    )


def test_html_foreign_cli_rejection(mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    oracle: Final = replace(ORACLES["html-foreign-grammar"], seeds=lambda: ["invalid"], floor=Floor(1, 1))
    mocker.patch.dict(ORACLES, {"html-foreign-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "html-foreign-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("*.json")), "VACUOUS RUN" in capsys.readouterr().err) == (2, [], True)
