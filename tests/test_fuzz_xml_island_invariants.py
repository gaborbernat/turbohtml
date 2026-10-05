from __future__ import annotations

import json
import random
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main
from fuzz.xml_island_oracles import (
    UnsupportedXmlIslandCaseError,
    xml_island_check,
    xml_island_controls,
    xml_island_generate,
    xml_island_seeds,
)

from turbohtml import CData, Comment, Element, Text, parse_xml

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("case", "source", "expected"),
    [
        pytest.param(
            "inside:plain:plain:1",
            "<Root><!--note--><![CDATA[Value]]>&lt;&amp;</Root>",
            [
                ("Element", "Root", "Document"),
                ("Comment", "note", "Root"),
                ("CData", "Value", "Root"),
                ("Text", "<&", "Root"),
            ],
            id="lexical-kinds",
        ),
        pytest.param(
            "outside:plain:plain:2",
            "<!--lead &amp;--><Root>" + "<!--note--><![CDATA[Value]]>&lt;&amp;" * 2 + "</Root><!--tail-->",
            [("Comment", "lead &amp;", "Document"), ("Element", "Root", "Document")]
            + [("Comment", "note", "Root"), ("CData", "Value", "Root"), ("Text", "<&", "Root")] * 2
            + [("Comment", "tail", "Document")],
            id="outside-root-attachment",
        ),
        pytest.param(
            "inside:markup:markup:1",
            "<Root><!--<x> &amp;--><![CDATA[<x>&amp;]]>&lt;&amp;</Root>",
            [
                ("Element", "Root", "Document"),
                ("Comment", "<x> &amp;", "Root"),
                ("CData", "<x>&amp;", "Root"),
                ("Text", "<&", "Root"),
            ],
            id="opaque-reference-looking-data",
        ),
        pytest.param(
            "inside:lines:lines:1",
            "<Root><!--a\r\nb\rc--><![CDATA[a\r\nb\rc]]>&lt;&amp;</Root>",
            [
                ("Element", "Root", "Document"),
                ("Comment", "a\nb\nc", "Root"),
                ("CData", "a\nb\nc", "Root"),
                ("Text", "<&", "Root"),
            ],
            id="literal-line-endings",
        ),
        pytest.param(
            "inside:plain:markup:3",
            "<Root>" + "<!--note--><![CDATA[<x>&amp;]]>&lt;&amp;" * 3 + "</Root>",
            [("Element", "Root", "Document")]
            + [("Comment", "note", "Root"), ("CData", "<x>&amp;", "Root"), ("Text", "<&", "Root")] * 3,
            id="three-lexical-groups",
        ),
    ],
)
def test_xml_island_literal_nodes(case: str, source: str, expected: list[tuple[str, str, str]]) -> None:
    assert (
        [
            (
                type(node).__name__,
                node.tag if isinstance(node, Element) else node.data,
                parent.tag if isinstance(parent := node.parent, Element) else "Document",
            )
            for node in parse_xml(source).descendants
            if isinstance(node, (Element, Comment, CData, Text))
        ],
        xml_island_check(case),
        xml_island_check(case, lambda _node: source.replace("\r\n", "\n").replace("\r", "\n")),
        xml_island_check(case, lambda _node: "<Root/>"),
    ) == (expected, None, None, "serialized XML islands differ from literals")


def test_xml_island_checks_first_parse() -> None:
    assert xml_island_check("inside:plain:plain:1", read=lambda _source: parse_xml("<Root/>")) == (
        "parsed XML islands differ from literals"
    )


def test_xml_island_rejects_unexpected_instruction() -> None:
    assert xml_island_check("inside:plain:plain:1", lambda _node: "<Root><?extra data?></Root>") == (
        "serialized XML islands differ from literals"
    )


def test_xml_island_rejects_changed_attachment() -> None:
    source: Final = "<!--lead &amp;--><Root><!--note--><![CDATA[Value]]>&lt;&amp;<!--tail--></Root>"
    assert xml_island_check("outside:plain:plain:1", lambda _node: source) == (
        "serialized XML islands differ from literals"
    )


def test_xml_island_checks_repeat_formatting() -> None:
    outputs: Final = iter([
        "<Root><!--note--><![CDATA[Value]]>&lt;&amp;</Root>",
        "<Root ><!--note--><![CDATA[Value]]>&lt;&amp;</Root>",
    ])
    assert xml_island_check("inside:plain:plain:1", lambda _node: next(outputs)) == (
        "XML island serialization changes on repeat"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("", id="missing-program"),
        pytest.param("around:plain:plain:1", id="attachment-pool"),
        pytest.param("inside:hyphens:plain:1", id="comment-pool"),
        pytest.param("inside:plain:delimiter:1", id="cdata-pool"),
        pytest.param("inside:plain:plain:0", id="zero-groups"),
        pytest.param("inside:plain:plain:4", id="node-budget"),
    ],
)
def test_xml_island_rejects_unsupported_grammar(case: str) -> None:
    with pytest.raises(UnsupportedXmlIslandCaseError):
        xml_island_check(case)
    with pytest.raises(OutOfScopeError):
        ORACLES["xml-island-grammar"].check(case)


def test_xml_island_production_sweep_and_bounds() -> None:
    rng: Final = random.Random(1018)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - Reproducible grammar samples.
    cases: Final = [*xml_island_seeds(), *(xml_island_generate(rng) for _ in range(100))]
    assert (
        len(xml_island_seeds()),
        {case.split(":")[index] for case in cases for index in (0, 1, 2)},
        max(int(case.rsplit(":", 1)[1]) for case in cases),
        all(xml_island_check(case) is None for case in cases),
        xml_island_controls(),
    ) == (
        54,
        {"inside", "outside", "plain", "markup", "lines"},
        3,
        True,
        {"CDATA converted to Text": True, "comment moved into Root": True, "CDATA reference decoded": True},
    )


def test_xml_island_cli_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "xml-island-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "54" in capsys.readouterr().out) == (0, [], True)


def test_xml_island_cli_emits_kind_loss(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["xml-island-grammar"],
        check=partial(xml_island_check, serialize=lambda _node: "<Root><!--note-->Value&lt;&amp;</Root>"),
        seeds=lambda: ["inside:plain:plain:1"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"xml-island-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "xml-island-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (
        1,
        1,
        "serialized XML islands differ from literals",
        1,
    )


def test_xml_island_cli_rejection_is_out_of_scope(
    mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oracle: Final = replace(ORACLES["xml-island-grammar"], seeds=lambda: ["invalid"], floor=Floor(1, 1))
    mocker.patch.dict(ORACLES, {"xml-island-grammar": oracle}, clear=True)
    status: Final = main(["--oracle", "xml-island-grammar", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("*.json")), "VACUOUS RUN" in capsys.readouterr().err) == (2, [], True)
