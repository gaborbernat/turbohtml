from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.structure_generators import (
    BudgetError,
    Generated,
    GenerationBudget,
    Production,
    ProductionFloorError,
    Reference,
    assert_production_floors,
    compile_grammar,
    generate,
    generation_sweep,
)
from fuzz.xml_structure_generators import (
    main,
    xml_document_check,
    xml_expected,
    xml_generate,
    xml_grammar,
    xml_raw_generate,
    xml_raw_inputs,
    xml_snapshot,
    xml_source_controls,
    xml_source_generate,
    xml_source_seeds,
    xml_structure_check,
)

from turbohtml import Html, HTMLParseError, parse_xml

if TYPE_CHECKING:
    from pathlib import Path


_CASES: Final = generation_sweep(xml_grammar(), budget=GenerationBudget(30, 120))


@pytest.mark.parametrize("case", _CASES, ids=[production.name for production in xml_grammar().productions])
def test_xml_structure_literals(case: Generated) -> None:
    assert xml_structure_check(case) is None


@pytest.mark.parametrize("case", _CASES, ids=[production.name for production in xml_grammar().productions])
def test_xml_structure_materialized_budget(case: Generated) -> None:
    root: Final = parse_xml(case.data.decode())
    nodes: Final = (root, *root.descendants)
    assert (len(nodes), max(len(tuple(node.ancestors)) for node in nodes)) == (case.nodes, case.depth)


def test_xml_structure_independent_parent_literals() -> None:
    case: Final = generate(xml_grammar(), random.Random(0), GenerationBudget(4, 6), force="xml:leaf:0")
    assert xml_expected(case) == (
        ("document", "", "", (), -1),
        ("element:html", "Root", "", (("id", "x"),), 0),
        ("element:html", "Leaf", "", (), 1),
        ("element:html", "Ref", "", (("target", "#x"),), 1),
    )


def test_xml_structure_changed_input() -> None:
    case: Final = replace(_CASES[0], data=_CASES[0].data.replace(b"Root", b"Wrong"))
    assert xml_structure_check(case) == "parsed XML differs from production literals"


def test_xml_structure_changed_serialization() -> None:
    assert (
        xml_structure_check(
            _CASES[0], serialize=lambda node: node.serialize(Html(xml=True)).replace('id="x"', 'id="wrong"')
        )
        == "serialized XML differs from production literals"
    )


@pytest.mark.parametrize("seed", range(64))
def test_xml_structure_random_bounds(seed: int) -> None:
    case: Final = xml_generate(random.Random(seed), 12, steps=60)
    assert (xml_structure_check(case), case.nodes <= 12, len(case.productions) <= 60) == (None, True, True)


@pytest.mark.parametrize("case", xml_raw_inputs(), ids=[case.productions[0] for case in xml_raw_inputs()])
def test_xml_structure_raw_rejection(case: Generated) -> None:
    with pytest.raises((UnicodeError, HTMLParseError, ValueError)):
        parse_xml(case.data.decode("utf-8"))


@pytest.mark.parametrize("raw", [False, True], ids=["valid", "raw"])
def test_xml_structure_materialized_corpus(tmp_path: Path, *, raw: bool) -> None:
    cases: Final = xml_raw_inputs() if raw else _CASES
    assert main(["--output", str(tmp_path), *(["--raw"] if raw else [])]) == 0
    assert {path.read_bytes() for path in tmp_path.iterdir()} == {case.data for case in cases}


def test_generation_zero_node_forced_path() -> None:
    grammar: Final = compile_grammar(
        (
            Production("root", "root", (b"<x", Reference("attribute", 0), b"/>"), 1, "test"),
            Production("empty", "attribute", (b"",), 0, "test"),
            Production("attribute", "attribute", (b' a="x"',), 0, "test"),
        ),
        "root",
    )
    assert generate(grammar, random.Random(0), GenerationBudget(1, 2), force="attribute").data == b'<x a="x"/>'


def test_generation_zero_node_cycle_terminates() -> None:
    grammar: Final = compile_grammar(
        (
            Production("cycle", "root", (b"x", Reference("root", 0)), 0, "test"),
            Production("leaf", "root", (b"z",), 0, "test"),
        ),
        "root",
    )
    case: Final = generate(grammar, random.Random(0), GenerationBudget(0, 2), force="cycle")
    assert (case.data, case.nodes, case.productions) == (b"xz", 0, ("cycle", "leaf"))


def test_generation_step_reservation_for_siblings() -> None:
    grammar: Final = compile_grammar(
        (
            Production("root", "root", (Reference("child", 0), Reference("child", 0)), 1, "test"),
            Production("cycle", "child", (b"x", Reference("child", 0)), 0, "test"),
            Production("leaf", "child", (b"z",), 0, "test"),
        ),
        "root",
    )
    case: Final = generate(grammar, random.Random(0), GenerationBudget(1, 4), force="cycle")
    assert (case.data, case.nodes, len(case.productions)) == (b"xzz", 1, 4)


@pytest.mark.parametrize("budget", [GenerationBudget(3, 120), GenerationBudget(30, 5)], ids=["nodes", "steps"])
def test_xml_structure_insufficient_budget(budget: GenerationBudget) -> None:
    with pytest.raises(BudgetError, match="cannot complete"):
        generate(xml_grammar(), random.Random(0), budget)


def test_xml_structure_snapshot_literal() -> None:
    assert xml_snapshot(parse_xml("<Root/>")) == (
        ("document", "", "", (), -1),
        ("element:html", "Root", "", (), 0),
    )


def test_xml_document_seed_consumers() -> None:
    assert [xml_document_check(source) for source in xml_source_seeds()] == [None] * len(_CASES)


def test_xml_document_generated_consumer() -> None:
    assert xml_document_check(xml_source_generate(random.Random(4))) is None


def test_xml_document_failure_controls() -> None:
    assert xml_source_controls() == {"dropped attribute": True, "changed parent": True}


def test_xml_document_custom_serializer() -> None:
    assert xml_document_check("<Root/>", lambda node: node.serialize(Html(xml=True))) is None


def test_xml_structure_custom_serializer() -> None:
    assert xml_structure_check(_CASES[0], serialize=lambda node: node.serialize(Html(xml=True))) is None


@pytest.mark.parametrize("arguments", [["--count", "-1"], ["--budget", "0"]], ids=["count", "budget"])
def test_xml_structure_cli_errors(tmp_path: Path, arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--output", str(tmp_path), *arguments])
    assert error.value.code == 2


def test_xml_structure_random_corpus(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path), "--count", "1", "--seed", "4"]) == 0
    assert {path.read_bytes() for path in tmp_path.iterdir()} == {xml_generate(random.Random(4)).data}


def test_xml_structure_disabled_production() -> None:
    name: Final = xml_grammar().productions[-1].name
    with pytest.raises(ProductionFloorError, match="production floors missed"):
        assert_production_floors(
            (case for case in _CASES if name not in case.productions),
            (production.name for production in xml_grammar().productions),
        )


def test_xml_raw_generate_literal() -> None:
    assert xml_raw_generate(random.Random(0), 4) == Generated(bytes.fromhex("4c09c2"), 0, 0, ("xml:raw:bytes",), ())


def test_xml_raw_generate_empty_budget() -> None:
    assert xml_raw_generate(random.Random(0), 0).data == b""


def test_xml_raw_generate_negative_budget() -> None:
    with pytest.raises(BudgetError, match="byte budget must be nonnegative"):
        xml_raw_generate(random.Random(0), -1)


def test_xml_raw_random_corpus(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path), "--raw", "--count", "1", "--byte-budget", "4"]) == 0
    assert {path.read_bytes() for path in tmp_path.iterdir()} == {bytes.fromhex("4c09c2")}


def test_xml_structure_identifier_lookup() -> None:
    root: Final = parse_xml(_CASES[0].data.decode())
    assert [(node.tag, dict(node.attrs)) for node in root.select("#x")] == [("Root", {"id": "x"})]
