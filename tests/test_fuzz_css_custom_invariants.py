from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.css_custom_oracles import (
    UnsupportedCssCustomCaseError,
    css_custom_check,
    css_custom_controls,
    css_custom_generate,
    css_custom_seeds,
)
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main

from turbohtml.clean import minify_css, minify_css_inline

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("case", "text", "expected"),
    [
        pytest.param(
            "sheet:ident:2:0", "a { --Foo : MiXeD ; --foo : UPPER ; }", "a{--Foo:MiXeD;--foo:UPPER}", id="name-case"
        ),
        pytest.param("inline:ident:1:0", " --Foo : MiXeD ; ", "--Foo:MiXeD", id="opaque-identifier"),
        pytest.param(
            "sheet:string:2:0",
            "a { --Foo : 'A B' ; --foo : 'x;y' ; }",
            "a{--Foo:'A B';--foo:'x;y'}",
            id="quoted-delimiter",
        ),
        pytest.param("inline:string:1:0", " --Foo : 'A B' ; ", "--Foo:'A B'", id="inline-string"),
    ],
)
def test_css_custom_literals_require_conservation_and_shortening(case: str, text: str, expected: str) -> None:
    printer: Final = minify_css if case.startswith("sheet:") else minify_css_inline
    assert (
        printer(text),
        printer(expected),
        css_custom_check(case),
        css_custom_check(case, lambda _text: expected),
        css_custom_check(case, lambda text: text),
    ) == (
        expected,
        expected,
        None,
        None,
        "custom-property tokens differ from literals",
    )


@pytest.mark.parametrize("quote", [pytest.param("'", id="single-quote"), pytest.param('"', id="double-quote")])
def test_css_custom_accepts_either_string_quote(quote: str) -> None:
    expected: Final = f"--Foo:{quote}A B{quote}"
    assert css_custom_check("inline:string:1:0", lambda _text: expected) is None


def test_css_custom_repeated_output_is_checked() -> None:
    expected: Final = "--Foo:MiXeD"
    assert css_custom_check("inline:ident:1:0", lambda text: expected if text != expected else expected + " ") == (
        "custom-property output changes on repeat"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("", id="missing-program"),
        pytest.param("sheet:ident:0:0", id="zero-declarations"),
        pytest.param("sheet:ident:5:0", id="node-budget"),
        pytest.param("sheet:string:1:8", id="payload-pool"),
        pytest.param("other:ident:1:0", id="root-production"),
        pytest.param("inline:color:1:0", id="leaf-production"),
    ],
)
def test_css_custom_rejects_unsupported_productions(case: str) -> None:
    with pytest.raises(UnsupportedCssCustomCaseError):
        css_custom_check(case)
    with pytest.raises(OutOfScopeError):
        ORACLES["css-custom-tokens"].check(case)


def test_css_custom_production_sweep_and_bounds() -> None:
    seeds: Final = css_custom_seeds()
    rng: Final = random.Random(1018)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - Reproduce grammar samples; no security tokens.
    generated: Final = [css_custom_generate(rng) for _ in range(100)]
    productions: Final = Counter(tuple(case.split(":")[:2]) for case in seeds)
    assert (
        len(seeds),
        productions,
        all(css_custom_check(case) is None for case in [*seeds, *generated]),
        max(int(case.split(":")[2]) for case in [*seeds, *generated]),
        css_custom_controls(),
    ) == (
        128,
        {("sheet", "ident"): 32, ("sheet", "string"): 32, ("inline", "ident"): 32, ("inline", "string"): 32},
        True,
        4,
        {"identity minifier": True, "folded name": True, "folded payload": True, "lost string content": True},
    )


def test_css_custom_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "css-custom-tokens", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "128" in capsys.readouterr().out) == (0, [], True)


def test_css_custom_cli_emits_token_loss(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["css-custom-tokens"],
        check=partial(css_custom_check, minify=lambda _text: ""),
        seeds=lambda: ["inline:ident:1:0"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"css-custom-tokens": oracle}, clear=True)
    status: Final = main(["--oracle", "css-custom-tokens", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (
        1,
        1,
        "custom-property tokens differ from literals",
        1,
    )


def test_css_custom_cli_rejection_is_out_of_scope(
    mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oracle: Final = replace(ORACLES["css-custom-tokens"], seeds=lambda: ["invalid"], floor=Floor(1, 1))
    mocker.patch.dict(ORACLES, {"css-custom-tokens": oracle}, clear=True)
    status: Final = main(["--oracle", "css-custom-tokens", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("*.json")), "VACUOUS RUN" in capsys.readouterr().err) == (2, [], True)
