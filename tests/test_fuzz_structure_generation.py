from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING, Final, cast

import pytest
from fuzz.round_trip_oracles import ORACLES
from fuzz.structure_generators import (
    BudgetError,
    Generated,
    Grammar,
    GrammarError,
    Identifier,
    Production,
    ProductionFloorError,
    Reference,
    assert_production_floors,
    compile_grammar,
    generate,
    generation_sweep,
    html_generate,
    html_grammar,
    main,
    write_corpus,
)

from turbohtml import Element, parse_fragment

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def grammar() -> Grammar:
    return compile_grammar(
        (
            Production("root", "root", (b"<div>", Reference("item", 2), Reference("item", 2), b"</div>"), 2, "test", 1),
            Production("leaf", "item", (b"<b>x</b>",), 2, "test", 1),
            Production("nested", "item", (b"<i>", Reference("item"), b"</i>"), 1, "test"),
        ),
        "root",
    )


def test_generation_reserves_siblings(grammar: Grammar) -> None:
    assert generate(grammar, random.Random(0), 6) == Generated(
        b"<div><b>x</b><b>x</b></div>", 6, 3, ("root", "leaf", "leaf"), ()
    )


def test_generation_leaf_uses_minimum(grammar: Grammar) -> None:
    assert generate(grammar, random.Random(1), 100, leaf=True) == Generated(
        b"<div><b>x</b><b>x</b></div>", 6, 3, ("root", "leaf", "leaf"), ()
    )


def test_generation_forces_nested(grammar: Grammar) -> None:
    assert generate(grammar, random.Random(2), 7, force="nested") == Generated(
        b"<div><i><b>x</b></i><b>x</b></div>", 7, 4, ("root", "nested", "leaf", "leaf"), ()
    )


def test_generation_forced_path_uses_minimum() -> None:
    compiled: Final = compile_grammar(
        (
            Production("heavy", "root", (b"<div><span></span><i>", Reference("item", 3), b"</i></div>"), 4, "test", 2),
            Production("small", "root", (b"<div>", Reference("item", 2), b"</div>"), 2, "test", 1),
            Production("leaf", "item", (b"<b>x</b>",), 2, "test", 1),
            Production("nested", "item", (b"<i>", Reference("item"), b"</i>"), 1, "test"),
        ),
        "root",
    )
    assert generate(compiled, random.Random(0), 5, force="nested") == Generated(
        b"<div><i><b>x</b></i></div>", 5, 4, ("small", "nested", "leaf"), ()
    )


@pytest.mark.parametrize(
    ("budget", "forced"), [pytest.param(5, None, id="root"), pytest.param(6, "nested", id="forced-path")]
)
def test_generation_rejects_insufficient_budget(grammar: Grammar, budget: int, forced: str | None) -> None:
    with pytest.raises(BudgetError, match="cannot complete"):
        generate(grammar, random.Random(0), budget, force=forced)


def test_generation_rejects_unknown_production(grammar: Grammar) -> None:
    with pytest.raises(GrammarError, match="unknown production"):
        generate(grammar, random.Random(0), force="missing")


@pytest.mark.parametrize(
    ("productions", "root", "message"),
    [
        pytest.param(
            (Production("same", "root", (b"x",), 1, "test"), Production("same", "root", (b"y",), 1, "test")),
            "root",
            "unique",
            id="duplicate-name",
        ),
        pytest.param((Production("negative", "root", (b"x",), -1, "test"),), "root", "nonnegative", id="negative-cost"),
        pytest.param(
            (Production("negative-height", "root", (b"x",), 1, "test", -1),),
            "root",
            "nonnegative",
            id="negative-height",
        ),
        pytest.param(
            (Production("negative-depth", "root", (Reference("root", -1),), 1, "test"),),
            "root",
            "nonnegative",
            id="negative-reference-depth",
        ),
        pytest.param((Production("root", "root", (b"x",), 1, "test"),), "missing", "unknown root", id="unknown-root"),
        pytest.param(
            (Production("root", "root", (Reference("missing"),), 1, "test"),),
            "root",
            "unknown symbols",
            id="unknown-symbol",
        ),
        pytest.param(
            (Production("root", "root", (b"x",), 1, "test"), Production("unused", "unused", (b"y",), 1, "test")),
            "root",
            "unreachable",
            id="unreachable",
        ),
        pytest.param(
            (Production("root", "root", (Reference("root"),), 1, "test"),),
            "root",
            "nonproductive",
            id="nonproductive-cycle",
        ),
    ],
)
def test_generation_rejects_invalid_grammar(productions: tuple[Production, ...], root: str, message: str) -> None:
    with pytest.raises(GrammarError, match=message):
        compile_grammar(productions, root)


def test_generation_sweep_forces_productions(grammar: Grammar) -> None:
    cases: Final = generation_sweep(grammar, 2)
    assert (len(cases), dict(assert_production_floors(cases, ("root", "leaf", "nested"), 2))) == (
        6,
        {"root": 6, "leaf": 12, "nested": 2},
    )


def test_generation_floor_detects_disabled_production(grammar: Grammar) -> None:
    with pytest.raises(ProductionFloorError, match="nested"):
        assert_production_floors((generate(grammar, random.Random(0), leaf=True),), ("nested",))


def test_generation_floor_rejects_zero(grammar: Grammar) -> None:
    with pytest.raises(ProductionFloorError, match="positive"):
        assert_production_floors((generate(grammar, random.Random(0)),), ("root",), 0)


def test_generation_sweep_rejects_zero(grammar: Grammar) -> None:
    with pytest.raises(ProductionFloorError, match="positive"):
        generation_sweep(grammar, 0)


def test_generation_identifiers_are_unique() -> None:
    compiled: Final = compile_grammar(
        (
            Production(
                "ids",
                "root",
                (
                    b'<div id="',
                    Identifier("first", definition=True),
                    b'"></div><div id="',
                    Identifier("second", definition=True),
                    b'"></div><div id="',
                    Identifier("third", definition=True),
                    b'"></div>',
                ),
                4,
                "test",
                1,
            ),
        ),
        "root",
    )
    case: Final = generate(compiled, random.Random(0))
    assert case == Generated(
        b'<div id="x"></div><div id="y"></div><div id="z"></div>',
        4,
        1,
        ("ids",),
        (("first", "x"), ("second", "y"), ("third", "z")),
    )


def test_generation_reference_before_definition() -> None:
    compiled: Final = compile_grammar(
        (
            Production(
                "before",
                "root",
                (
                    b'<a href="#',
                    Identifier("target", definition=False),
                    b'">x</a><div id="',
                    Identifier("target", definition=True),
                    b'"></div>',
                ),
                4,
                "test",
                2,
            ),
        ),
        "root",
    )
    assert generate(compiled, random.Random(0)) == Generated(
        b'<a href="#x">x</a><div id="x"></div>', 4, 2, ("before",), (("target", "x"),)
    )


@pytest.mark.parametrize(
    ("parts", "message"),
    [
        pytest.param(
            tuple(Identifier(name, definition=True) for name in ("first", "second", "third", "fourth")),
            "exhausted",
            id="pool-exhausted",
        ),
        pytest.param(
            (Identifier("first", definition=True), Identifier("first", definition=True)),
            "duplicate identifier",
            id="duplicate-definition",
        ),
        pytest.param((Identifier("missing", definition=False),), "undefined identifiers", id="undefined-reference"),
    ],
)
def test_generation_rejects_invalid_identifiers(parts: tuple[Identifier, ...], message: str) -> None:
    compiled: Final = compile_grammar((Production("ids", "root", parts, 1, "test"),), "root")
    with pytest.raises(GrammarError, match=message):
        generate(compiled, random.Random(0))


@pytest.mark.parametrize(
    ("budget", "force", "expected"),
    [
        pytest.param(3, None, Generated(b"<div>x</div>", 3, 2, ("root", "leaf"), ()), id="minimum"),
        pytest.param(
            6,
            "cycle",
            Generated(b"<div><i><div>x</div></i></div>", 6, 5, ("root", "cycle", "root", "leaf"), ()),
            id="forced-cycle",
        ),
    ],
)
def test_generation_productive_cycle_terminates(budget: int, force: str | None, expected: Generated) -> None:
    compiled: Final = compile_grammar(
        (
            Production("root", "root", (b"<div>", Reference("item", 2), b"</div>"), 2, "test", 1),
            Production("cycle", "item", (b"<i>", Reference("root"), b"</i>"), 1, "test"),
            Production("leaf", "item", (b"x",), 1, "test"),
        ),
        "root",
    )
    assert generate(compiled, random.Random(0), budget, force=force) == expected


@pytest.fixture
def depth_grammars() -> tuple[Grammar, ...]:
    return tuple(
        compile_grammar(
            (
                Production(
                    "root",
                    "root",
                    (b"<div>" * level, Reference("item", level + 1), b"</div>" * level),
                    level + 1,
                    "test",
                    level,
                ),
                Production("leaf", "item", (b"<b>x</b>",), 2, "test", 1),
                Production("nested", "item", (b"<i>", Reference("item"), b"</i>"), 1, "test"),
            ),
            "root",
        )
        for level in (1, 8)
    )


def test_generation_depth_decay(depth_grammars: tuple[Grammar, ...]) -> None:
    counts: Final = [
        sum(generate(compiled, random.Random(seed), 100).productions.count("nested") for seed in range(128))
        for compiled in depth_grammars
    ]
    assert counts[0] > counts[1]


def test_generation_corpus_deduplicates(grammar: Grammar, tmp_path: Path) -> None:
    case: Final = generate(grammar, random.Random(0), leaf=True)
    assert write_corpus((case, case), tmp_path / "corpus") == 1


def test_generation_corpus_contains_materialized_bytes(grammar: Grammar, tmp_path: Path) -> None:
    case: Final = generate(grammar, random.Random(0), leaf=True)
    write_corpus((case,), tmp_path)
    assert (tmp_path / hashlib.sha256(case.data).hexdigest()).read_bytes() == b"<div><b>x</b><b>x</b></div>"


def test_generation_raw_bytes_survive_export(tmp_path: Path) -> None:
    compiled: Final = compile_grammar((Production("raw", "root", (b"\xff",), 1, "test"),), "root")
    case: Final = generate(compiled, random.Random(0))
    write_corpus((case,), tmp_path)
    assert (tmp_path / hashlib.sha256(b"\xff").hexdigest()).read_bytes() == b"\xff"


_HTML_CASES: Final = generation_sweep(html_grammar())
_HTML_INPUTS: Final = (*_HTML_CASES, *(html_generate(random.Random(seed)) for seed in range(128)))


@pytest.mark.parametrize("case", [pytest.param(case, id=f"case-{index}") for index, case in enumerate(_HTML_INPUTS)])
def test_generation_html_node_accounting(case: Generated) -> None:
    root: Final = parse_fragment(case.data.decode("utf-8"))
    assert sum(1 for _ in root.descendants) + 1 == case.nodes


@pytest.mark.parametrize("case", [pytest.param(case, id=f"case-{index}") for index, case in enumerate(_HTML_INPUTS)])
def test_generation_html_depth_accounting(case: Generated) -> None:
    root: Final = parse_fragment(case.data.decode("utf-8"))
    assert (
        max(sum(isinstance(ancestor, Element) for ancestor in node.ancestors) for node in root.descendants)
        == case.depth
    )


@pytest.mark.parametrize("case", [pytest.param(case, id=f"case-{index}") for index, case in enumerate(_HTML_INPUTS)])
def test_generation_html_references_bind(case: Generated) -> None:
    root: Final = parse_fragment(case.data.decode("utf-8"))
    references: Final = [
        cast("str", node.attrs.get("href") or node.attrs.get("src")) for node in root.select('[href^="#"],[src^="#"]')
    ]
    assert (bool(references), set(references)) == (True, {"#x"})


@pytest.mark.parametrize("case", [pytest.param(case, id=f"case-{index}") for index, case in enumerate(_HTML_INPUTS)])
def test_generation_html_reference_target(case: Generated) -> None:
    root: Final = parse_fragment(case.data.decode("utf-8"))
    assert [
        (node.tag, tuple(sorted(node.attrs.items())), sum(isinstance(ancestor, Element) for ancestor in node.ancestors))
        for node in root.select("#x")
    ] == [("div", (("id", "x"),), 1)]


@pytest.mark.parametrize("case", [pytest.param(case, id=f"case-{index}") for index, case in enumerate(_HTML_INPUTS)])
def test_generation_html_small_identifier_pool(case: Generated) -> None:
    root: Final = parse_fragment(case.data.decode("utf-8"))
    assert (
        {cast("str", node.attrs["id"]) for node in root.select("[id]")} <= {"x", "y", "z"},
        {token for node in root.select("[class]") for token in cast("list[str]", node.attrs["class"])}
        <= {"a", "b", "c"},
    ) == (True, True)


def test_generation_html_minimum() -> None:
    assert html_generate(random.Random(0), 5) == Generated(
        b'<div id="x">x<a href="#x">x</a></div>',
        5,
        3,
        ("html:root", "html:text:0"),
        (("target", "x"),),
    )


def test_generation_html_budget() -> None:
    assert max(case.nodes for case in _HTML_INPUTS) <= 30


def test_generation_html_all_declared_productions_fire() -> None:
    grammar: Final = html_grammar()
    assert set(assert_production_floors(_HTML_CASES, (production.name for production in grammar.productions))) == {
        production.name for production in grammar.productions
    }


@pytest.mark.parametrize(
    ("name", "origin"),
    [
        pytest.param(
            "html:tag:span",
            "https://github.com/googleprojectzero/domato/blob/fadff396cc45d521cc594d3e2396e27e887b1963/html_tags.py",
            id="pinned-tag",
        ),
        pytest.param(
            "html:attribute:title:0",
            "https://github.com/tox-dev/turbohtml/blob/6a8722d7614a69df4b6ca6c8563f62d00f0837c1/tools/fuzz/round_trip_oracles.py",
            id="pinned-local-value",
        ),
        pytest.param("html:tag:svg", "https://html.spec.whatwg.org/multipage/parsing.html", id="foreign-boundary"),
    ],
)
def test_generation_html_provenance(name: str, origin: str) -> None:
    assert next(production.origin for production in html_grammar().productions if production.name == name) == origin


def test_generation_general_html_adapter() -> None:
    assert ORACLES["html-fixpoint"].generate(random.Random(0)) == '<frameset id="x"><frame src="#x"></frameset>'


def test_generation_cli_exports(tmp_path: Path) -> None:
    assert (
        main(["--output", str(tmp_path), "--count", "2", "--budget", "5"]),
        {path.read_bytes() for path in tmp_path.iterdir()},
    ) == (
        0,
        {b'<div id="x">x<a href="#x">x</a></div>', b'<div id="x"><img src="a b"><a href="#x">x</a></div>'},
    )


def test_generation_cli_sweep(tmp_path: Path) -> None:
    main(["--output", str(tmp_path), "--count", "1", "--sweep"])
    assert {path.read_bytes() for path in tmp_path.iterdir()} == {case.data for case in _HTML_CASES}


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        pytest.param(["--count", "0"], "count must be positive", id="bad-count"),
        pytest.param(["--budget", "4"], "cannot complete", id="insufficient-budget"),
    ],
)
def test_generation_cli_rejects_invalid_bounds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], arguments: list[str], message: str
) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--output", str(tmp_path), *arguments])
    assert (error.value.code, message in capsys.readouterr().err) == (2, True)
