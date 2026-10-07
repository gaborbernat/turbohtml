from __future__ import annotations

import hashlib
import json
import random
from dataclasses import replace
from typing import TYPE_CHECKING, Final, cast

import pytest
from fuzz.encoding_structure_generators import (
    EncodingSeed,
    encoding_check,
    encoding_controls,
    encoding_decoded,
    encoding_expected,
    encoding_generate,
    encoding_grammar,
    encoding_manifest,
    encoding_profile,
    main,
)
from fuzz.structure_generators import (
    BudgetError,
    Generated,
    GenerationBudget,
    ProductionFloorError,
    assert_production_floors,
    generate,
    generation_sweep,
)

from turbohtml import parse

if TYPE_CHECKING:
    from pathlib import Path


_CASES: Final = generation_sweep(encoding_grammar(), budget=GenerationBudget(32, 128))
_NAMES: Final = [production.name for production in encoding_grammar().productions]


@pytest.mark.parametrize("case", _CASES, ids=_NAMES)
def test_encoding_structure_literals(case: Generated) -> None:
    assert encoding_check(case) is None


@pytest.mark.parametrize("case", _CASES, ids=_NAMES)
def test_encoding_structure_materialized_budget(case: Generated) -> None:
    profile: Final = encoding_profile(case)
    document: Final = (
        parse(case.data, detect_encoding=True) if profile.sniff else parse(case.data, encoding=profile.encoding)
    )
    nodes: Final = (document, *document.descendants)
    assert (len(nodes), max(len(tuple(node.ancestors)) for node in nodes)) == (case.nodes, case.depth)


def test_encoding_structure_inventory() -> None:
    assert (
        len([name for name in _NAMES if name.startswith("encoding:codec:")]),
        len([name for name in _NAMES if name.startswith("encoding:meta:")]),
        len([name for name in _NAMES if name.startswith("encoding:bom:")]),
        len(_NAMES),
    ) == (41, 228, 3, 467)


@pytest.mark.parametrize(
    ("name", "encoding", "codec", "text"),
    [
        pytest.param("encoding:codec:utf-8", "UTF-8", "whatwg-utf-8", "é", id="utf8"),
        pytest.param(
            "encoding:codec:x-user-defined", "x-user-defined", "whatwg-x-user-defined", "\uf780", id="private"
        ),
        pytest.param("encoding:meta:x-user-defined", "windows-1252", "whatwg-windows-1252", "€", id="meta-remap"),
        pytest.param("encoding:meta:utf-16le", "UTF-8", "whatwg-utf-8", "é", id="meta-utf16"),
        pytest.param("encoding:bom:utf-16le", "UTF-16LE", "whatwg-utf-16le", "é", id="bom-utf16"),
    ],
)
def test_encoding_structure_forced_specimen(name: str, encoding: str, codec: str, text: str) -> None:
    case: Final = generate(encoding_grammar(), random.Random(0), GenerationBudget(32, 128), force=name)
    profile: Final = encoding_profile(case)
    assert (
        profile.encoding,
        profile.codec,
        [record[2] for record in encoding_expected(case) if record[0] == "text"],
    ) == (encoding, codec, [text, "x"])


def test_encoding_structure_utf16_binding_bytes() -> None:
    case: Final = generate(encoding_grammar(), random.Random(0), 16, force="encoding:codec:utf-16le")
    assert (case.data, case.bindings) == (
        '<div id="x"><p>é</p><a href="#x">x</a></div>'.encode("utf-16-le"),
        (("anchor", "x"),),
    )


def test_encoding_structure_independent_parents() -> None:
    case: Final = generate(encoding_grammar(), random.Random(0), 16, force="encoding:codec:utf-8")
    assert encoding_expected(case) == (
        ("document", "", "", (), -1),
        ("element:html", "html", "", (), 0),
        ("element:html", "head", "", (), 1),
        ("element:html", "body", "", (), 1),
        ("element:html", "div", "", (("id", "x"),), 3),
        ("element:html", "p", "", (), 4),
        ("text", "", "é", (), 5),
        ("element:html", "a", "", (("href", "#x"),), 4),
        ("text", "", "x", (), 7),
    )


def test_encoding_structure_empty_replacement() -> None:
    case: Final = generate(encoding_grammar(), random.Random(0), 4, force="encoding:codec:replacement:empty")
    assert (case.data, case.nodes, case.depth, encoding_decoded(case)) == (b"", 4, 2, "")


def test_encoding_structure_first_decode_loss() -> None:
    case: Final = generate(encoding_grammar(), random.Random(0), 16, force="encoding:codec:utf-8")
    assert encoding_check(replace(case, data=case.data.replace(b"\xc3\xa9", b"x"))) == (
        "decoded bytes differ from production literals"
    )


def test_encoding_structure_failure_controls() -> None:
    assert encoding_controls() == {
        "missing decoded text": True,
        "changed parsed tree": True,
        "wrong sniffed codec": True,
    }


@pytest.mark.parametrize("seed", range(32))
def test_encoding_structure_random_budget(seed: int) -> None:
    case: Final = encoding_generate(random.Random(seed), 16, steps=32)
    assert (encoding_check(case), case.nodes <= 16, len(case.productions) <= 32) == (None, True, True)


@pytest.mark.parametrize("budget", [GenerationBudget(3, 128), GenerationBudget(32, 0)], ids=["nodes", "steps"])
def test_encoding_structure_insufficient_budget(budget: GenerationBudget) -> None:
    with pytest.raises(BudgetError, match="cannot complete"):
        generate(encoding_grammar(), random.Random(0), budget)


def test_encoding_structure_production_floors() -> None:
    assert_production_floors(_CASES, _NAMES)
    with pytest.raises(ProductionFloorError, match="production floors missed"):
        assert_production_floors((case for case in _CASES if "content:UTF-8:siblings" not in case.productions), _NAMES)


def test_encoding_structure_manifest_context() -> None:
    case: Final = generate(encoding_grammar(), random.Random(0), 16, force="encoding:codec:utf-8")
    assert encoding_manifest(case) == {
        "path": hashlib.sha256(case.data).hexdigest(),
        "encoding": "UTF-8",
        "codec": "whatwg-utf-8",
        "declared": None,
        "sniff": False,
        "bom": "",
        "decoded": '<div id="x"><p>é</p><a href="#x">x</a></div>',
        "productions": ["encoding:codec:utf-8", "content:UTF-8:empty"],
        "origins": [
            "https://encoding.spec.whatwg.org/#utf-8-decoder",
            "https://encoding.spec.whatwg.org#concept-stream-end",
        ],
        "bindings": {"anchor": "x"},
        "nodes": 9,
        "depth": 5,
    }


@pytest.mark.parametrize("count", [0, 1], ids=["forced-sweep", "random"])
def test_encoding_structure_materialized_corpus(tmp_path: Path, count: int) -> None:
    main(["--output", str(tmp_path), "--count", str(count)])
    manifest: Final = cast("list[EncodingSeed]", json.loads((tmp_path / "manifest.json").read_text()))
    cases: Final = (encoding_generate(random.Random(0)),) if count else _CASES
    assert (
        manifest,
        {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.name != "manifest.json"},
    ) == (
        [encoding_manifest(case) for case in cases],
        {hashlib.sha256(case.data).hexdigest(): case.data for case in cases},
    )


@pytest.mark.parametrize(
    "arguments",
    [["--count", "-1"], ["--budget", "0"], ["--steps", "0"]],
    ids=["negative-count", "node-budget", "step-budget"],
)
def test_encoding_structure_cli_errors(tmp_path: Path, arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--output", str(tmp_path), *arguments])
    assert error.value.code == 2
