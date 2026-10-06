from __future__ import annotations

import json
import random
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main
from fuzz.xml_grammar_oracles import (
    UnsupportedXmlLiteralCaseError,
    xml_literal_check,
    xml_literal_controls,
    xml_literal_generate,
    xml_literal_seeds,
)

from turbohtml import parse_xml

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("case", "source", "expected"),
    [
        pytest.param(
            "p:Leaf:double:1:plain",
            '<Root xmlns:p="urn:p"><p:Leaf p:Key="Value" Key="Other">MiXeD</p:Leaf></Root>',
            [("Root", {"xmlns:p": "urn:p"}, "MiXeD"), ("p:Leaf", {"p:Key": "Value", "Key": "Other"}, "MiXeD")],
            id="qualified-case",
        ),
        pytest.param(
            "p:Leaf:double:3:plain",
            '<Root xmlns:p="urn:p">' + '<p:Leaf p:Key="Value" Key="Other">MiXeD</p:Leaf>' * 3 + "</Root>",
            [("Root", {"xmlns:p": "urn:p"}, "MiXeDMiXeDMiXeD")]
            + [("p:Leaf", {"p:Key": "Value", "Key": "Other"}, "MiXeD")] * 3,
            id="three-identical-children",
        ),
        pytest.param(
            "P:leaf:single:1:escaped",
            "<Root xmlns:P='urn:P'><P:leaf P:Key='&quot;&apos;&amp;&lt;' Key='Other'>&amp;&lt;&gt;</P:leaf></Root>",
            [("Root", {"xmlns:P": "urn:P"}, "&<>"), ("P:leaf", {"P:Key": "\"'&<", "Key": "Other"}, "&<>")],
            id="escaped-delimiters",
        ),
        pytest.param(
            "p:Leaf:double:1:literal",
            '<Root xmlns:p="urn:p"><p:Leaf p:Key="a\tb\r\nc\rd" Key="Other">a\tb\r\nc\rd</p:Leaf></Root>',
            [
                ("Root", {"xmlns:p": "urn:p"}, "a\tb\nc\nd"),
                ("p:Leaf", {"p:Key": "a b c d", "Key": "Other"}, "a\tb\nc\nd"),
            ],
            id="literal-whitespace",
        ),
        pytest.param(
            "p:Leaf:double:1:numeric",
            '<Root xmlns:p="urn:p"><p:Leaf p:Key="a&#9;b&#10;c&#13;d" Key="Other">a&#9;b&#10;c&#13;d</p:Leaf></Root>',
            [
                ("Root", {"xmlns:p": "urn:p"}, "a\tb\nc\rd"),
                ("p:Leaf", {"p:Key": "a\tb\nc\rd", "Key": "Other"}, "a\tb\nc\rd"),
            ],
            id="referenced-whitespace",
        ),
    ],
)
def test_xml_literal_trees(case: str, source: str, expected: list[tuple[str, dict[str, str], str]]) -> None:
    assert (
        [(node.tag, dict(node.attrs), node.text) for node in parse_xml(source).iter_elements()],
        xml_literal_check(case),
        xml_literal_check(case, lambda _node: source),
        xml_literal_check(case, lambda _node: "<Root/>"),
    ) == (expected, None, None, "serialized XML tree differs from literals")


def test_xml_literal_rejects_nested_second_child() -> None:
    source: Final = (
        '<Root xmlns:p="urn:p"><p:Leaf p:Key="Value" Key="Other">MiXeD'
        '<p:Leaf p:Key="Value" Key="Other">MiXeD</p:Leaf></p:Leaf></Root>'
    )
    assert xml_literal_check("p:Leaf:double:2:plain", lambda _node: source) == (
        "serialized XML tree differs from literals"
    )


def test_xml_literal_checks_first_parse() -> None:
    assert xml_literal_check("p:Leaf:double:1:plain", read=lambda _source: parse_xml("<Root/>")) == (
        "parsed XML tree differs from literals"
    )


def test_xml_literal_rejects_unexpected_comment() -> None:
    assert xml_literal_check("p:Leaf:double:1:plain", lambda _node: "<Root><!--extra--></Root>") == (
        "serialized XML tree differs from literals"
    )


def test_xml_literal_checks_repeat_formatting() -> None:
    outputs: Final = iter([
        '<Root xmlns:p="urn:p"><p:Leaf p:Key="Value" Key="Other">MiXeD</p:Leaf></Root>',
        "<Root xmlns:p='urn:p'><p:Leaf p:Key='Value' Key='Other'>MiXeD</p:Leaf></Root>",
    ])
    assert (
        xml_literal_check("p:Leaf:double:1:plain", lambda _node: next(outputs)) == "XML serialization changes on repeat"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("", id="missing-program"),
        pytest.param("q:Leaf:double:1:plain", id="prefix-pool"),
        pytest.param("p:Other:double:1:plain", id="name-pool"),
        pytest.param("p:Leaf:bare:1:plain", id="quote-pool"),
        pytest.param("p:Leaf:double:0:plain", id="zero-children"),
        pytest.param("p:Leaf:double:4:plain", id="node-budget"),
        pytest.param("p:Leaf:double:1:raw", id="terminal-pool"),
    ],
)
def test_xml_literal_rejects_unsupported_grammar(case: str) -> None:
    with pytest.raises(UnsupportedXmlLiteralCaseError):
        xml_literal_check(case)
    with pytest.raises(OutOfScopeError):
        ORACLES["xml-literal-grammar"].check(case)


def test_xml_literal_production_sweep_and_bounds() -> None:
    rng: Final = random.Random(1018)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - Reproducible grammar samples.
    cases: Final = [*xml_literal_seeds(), *(xml_literal_generate(rng) for _ in range(100))]
    assert (
        len(xml_literal_seeds()),
        {case.split(":")[index] for case in cases for index in (0, 1, 2, 4)},
        max(int(case.split(":")[3]) for case in cases),
        all(xml_literal_check(case) is None for case in cases),
        xml_literal_controls(),
    ) == (
        96,
        {"p", "P", "Leaf", "leaf", "single", "double", "plain", "escaped", "literal", "numeric"},
        3,
        True,
        {
            "nested second child": True,
            "changed declaration": True,
            "changed qualified name": True,
            "referenced whitespace folded": True,
        },
    )


def test_xml_literal_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "xml-literal-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "96" in capsys.readouterr().out) == (0, [], True)


def test_xml_literal_cli_emits_changed_declaration(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["xml-literal-grammar"],
        check=partial(
            xml_literal_check,
            serialize=lambda _node: '<Root xmlns:p="urn:wrong"><p:Leaf p:Key="Value" Key="Other">MiXeD</p:Leaf></Root>',
        ),
        seeds=lambda: ["p:Leaf:double:1:plain"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"xml-literal-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "xml-literal-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (
        1,
        1,
        "serialized XML tree differs from literals",
        1,
    )


def test_xml_literal_cli_rejection_is_out_of_scope(
    mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oracle: Final = replace(ORACLES["xml-literal-grammar"], seeds=lambda: ["invalid"], floor=Floor(1, 1))
    mocker.patch.dict(ORACLES, {"xml-literal-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "xml-literal-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("*.json")), "VACUOUS RUN" in capsys.readouterr().err) == (2, [], True)
