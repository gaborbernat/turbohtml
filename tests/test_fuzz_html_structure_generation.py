from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING, Final, cast

import pytest
from fuzz.html_generation_tables import ATTRIBUTE_VALUE_RULES, HTML_TAGS, TAG_ATTRIBUTE_RULES
from fuzz.html_structure_generators import HtmlVocabulary, html_document, html_generate, html_grammar_complete, main
from fuzz.structure_generators import (
    Generated,
    GrammarError,
    ProductionFloorError,
    assert_production_floors,
    generate,
    generation_sweep,
    write_corpus,
)

from turbohtml import Document, Element, Node, Text, parse, parse_fragment

if TYPE_CHECKING:
    from pathlib import Path

_GRAMMAR: Final = html_grammar_complete()
_SWEEP: Final = generation_sweep(_GRAMMAR)
_CASES: Final = (*_SWEEP, *(html_generate(random.Random(seed)) for seed in range(64)))
_CASE_IDS: Final = [f"production-{index}" for index in range(len(_CASES))]


@pytest.fixture
def root(request: pytest.FixtureRequest) -> Node:
    case: Final = cast("Generated", request.param)
    return parse(case.data.decode("utf-8")) if html_document(case) else parse_fragment(case.data.decode("utf-8"))


@pytest.mark.parametrize(("root", "case"), [(case, case) for case in _CASES], indirect=["root"], ids=_CASE_IDS)
def test_html_complete_node_accounting(root: Node, case: Generated) -> None:
    assert 1 + sum(1 for _ in root.descendants) == case.nodes


@pytest.mark.parametrize(("root", "case"), [(case, case) for case in _CASES], indirect=["root"], ids=_CASE_IDS)
def test_html_complete_depth_accounting(root: Node, case: Generated) -> None:
    assert (
        max(
            sum(isinstance(root, Document) or not isinstance(ancestor, Document) for ancestor in node.ancestors)
            for node in (root, *root.descendants)
        )
        == case.depth
    )


@pytest.mark.parametrize("root", _CASES, indirect=True, ids=_CASE_IDS)
def test_html_complete_identifier_target(root: Node) -> None:
    assert [element.tag for element in root.select('[id="x"]')] in [["div"], ["html"], ["frameset"]]


@pytest.mark.parametrize(
    ("line", "attribute", "expected"),
    [
        pytest.param(82, "aria-activedescendant", "x", id="active-descendant"),
        pytest.param(93, "aria-controls", "x", id="controls"),
        pytest.param(95, "aria-describedby", "x", id="description"),
        pytest.param(108, "aria-flowto", "x", id="flow"),
        pytest.param(114, "aria-help", "x", id="help"),
        pytest.param(122, "aria-labeledby", "x", id="legacy-label"),
        pytest.param(124, "aria-labelledby", "x", id="label"),
        pytest.param(141, "aria-owns", "x", id="owns"),
        pytest.param(274, "contextmenu", "x", id="context-menu"),
        pytest.param(372, "for", "x", id="label-for"),
        pytest.param(374, "form", "x", id="form"),
        pytest.param(385, "formtarget", "x", id="form-target"),
        pytest.param(407, "headers", ["x"], id="headers"),
        pytest.param(477, "itemref", "x", id="item-reference"),
        pytest.param(729, "list", "x", id="datalist"),
        pytest.param(771, "menu", "x", id="menu"),
        pytest.param(1011, "select", "#x", id="selector"),
        pytest.param(1069, "target", "x", id="target"),
        pytest.param(1326, "usemap", "#x", id="image-map"),
    ],
)
def test_html_complete_table_identifier_reference(line: int, attribute: str, expected: str | list[str]) -> None:
    case: Final = generate(_GRAMMAR, random.Random(0), force=f"html:domato:value:{line}")
    root: Final = parse_fragment(case.data.decode("utf-8"))
    assert (root.select(f"[{attribute}]")[0].attrs[attribute], root.select('[id="x"]')[0].tag) == (expected, "div")


@pytest.mark.parametrize(
    ("line", "attribute", "expected"),
    [
        pytest.param(15, "accept-charset", ["x"], id="charset-delegation"),
        pytest.param(16, "accept-charset", ["UTF-7"], id="charset-alternative"),
        pytest.param(28, "autocomplete", "on", id="onoff-helper"),
        pytest.param(29, "autocomplete", "off", id="onoff-alternative"),
        pytest.param(243, "class", ["a"], id="class-pool"),
        pytest.param(1063, "style", "color: red; color: red; color: red; color: red; color: red", id="css-import"),
    ],
)
def test_html_complete_value_alternatives(line: int, attribute: str, expected: str | list[str]) -> None:
    case: Final = generate(_GRAMMAR, random.Random(0), force=f"html:domato:value:{line}")
    assert parse_fragment(case.data.decode("utf-8")).select(f"[{attribute}]")[0].attrs[attribute] == expected


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        pytest.param("frame", ["html", "head", "frameset", "frame"], id="frame-document"),
        pytest.param("frameset", ["html", "head", "frameset", "frame"], id="frameset-document"),
        pytest.param("html", ["html", "head", "title", "body", "a"], id="html-document"),
        pytest.param("head", ["html", "head", "title", "body", "a"], id="head-document"),
        pytest.param("body", ["html", "head", "title", "body", "a"], id="body-document"),
        pytest.param("plaintext", ["div", "a", "plaintext"], id="plaintext-last"),
    ],
)
def test_html_complete_special_tag_materialization(tag: str, expected: list[str]) -> None:
    name: Final = f"html:domato:tag:{tag}"
    case: Final = generate(_GRAMMAR, random.Random(0), force=name if tag == "plaintext" else "html:document:" + name)
    root: Final = parse(case.data.decode("utf-8")) if html_document(case) else parse_fragment(case.data.decode("utf-8"))
    assert [node.tag for node in root.descendants if isinstance(node, Element)] == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param(
            "html:hostile:formatting",
            [
                ("div", "html", 0),
                ("b", "html", 1),
                ("i", "html", 2),
                ("x", "text", 3),
                ("i", "html", 1),
                ("y", "text", 5),
                ("a", "html", 1),
                ("x", "text", 7),
            ],
            id="adoption",
        ),
        pytest.param(
            "html:hostile:near-miss",
            [
                ("div", "html", 0),
                ("span", "html", 1),
                ("x", "text", 2),
                ("b", "html", 2),
                ("y", "text", 4),
                ("a", "html", 1),
                ("x", "text", 6),
            ],
            id="near-miss",
        ),
        *(
            pytest.param(
                f"html:foreign:svg:{tag}",
                [
                    ("div", "html", 0),
                    ("svg", "svg", 1),
                    (tag, "svg", 2),
                    ("p", "html", 3),
                    ("x", "text", 4),
                    ("circle", "svg", 2),
                    ("a", "html", 1),
                    ("x", "text", 7),
                ],
                id=tag,
            )
            for tag in ("foreignObject", "desc", "title")
        ),
    ],
)
def test_html_complete_literal_foreign_and_hostile_shape(name: str, expected: list[tuple[str, str, int]]) -> None:
    case: Final = generate(_GRAMMAR, random.Random(0), force=name)
    root: Final = parse_fragment(case.data.decode("utf-8"))
    nodes: Final = [root, *root.descendants]
    assert [
        (node.data, "text", nodes.index(cast("Node", node.parent)))
        if isinstance(node, Text)
        else (
            cast("Element", node).tag,
            cast("Element", node).namespace.name.lower(),
            nodes.index(cast("Node", node.parent)),
        )
        for node in nodes[1:]
    ] == expected


def test_html_complete_all_table_productions_fire() -> None:
    counts: Final = assert_production_floors(_SWEEP, (production.name for production in _GRAMMAR.productions))
    assert (
        sum(name.startswith(("html:domato:tag:", "html:document:html:domato:tag:")) for name in counts),
        sum(name.startswith("html:domato:value:") for name in counts),
        sum("html:domato:tag-attribute:" in name for name in counts),
    ) == (len(HTML_TAGS), len(ATTRIBUTE_VALUE_RULES), len(TAG_ATTRIBUTE_RULES))


def test_html_complete_disabled_production_fails_floor() -> None:
    cases: Final = tuple(case for case in _SWEEP if "html:hostile:formatting" not in case.productions)
    with pytest.raises(ProductionFloorError, match="html:hostile:formatting"):
        assert_production_floors(cases, (production.name for production in _GRAMMAR.productions))


def test_html_complete_exports_input_bytes(tmp_path: Path) -> None:
    case: Final = generate(_GRAMMAR, random.Random(0), force="html:hostile:near-miss")
    write_corpus((case, case), tmp_path)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {
        hashlib.sha256(case.data).hexdigest(): b'<div id="x"><span>x</spna><b>y</b></span><a href="#x">x</a></div>'
    }


@pytest.mark.parametrize(
    ("vocabulary", "message"),
    [
        pytest.param(
            HtmlVocabulary(("span",), (), ((1, "missing", "x"),), ()), "no emitting attribute", id="unused-value"
        ),
        pytest.param(
            HtmlVocabulary(("span",), ((1, "attribute_x", 'x="<missing>"'),), (), ()),
            "unproductive value",
            id="unknown-value",
        ),
        pytest.param(
            HtmlVocabulary(("span",), (), (), ((1, "unknown_attribute", "x"),)),
            "no tag materialization",
            id="unknown-tag",
        ),
        pytest.param(
            HtmlVocabulary(("span",), ((1, "attribute_x", 'x="<import from=missing symbol=x>"'),), (), ()),
            "unsupported grammar import",
            id="unknown-import",
        ),
    ],
)
def test_html_complete_rejects_incomplete_tables(vocabulary: HtmlVocabulary, message: str) -> None:
    with pytest.raises(GrammarError, match=message):
        html_grammar_complete(vocabulary)


def test_html_complete_productive_value_cycle_terminates() -> None:
    grammar: Final = html_grammar_complete(
        HtmlVocabulary(
            ("span",),
            ((1, "attribute_x", 'x="<value>"'),),
            ((1, "value", "<helper>"), (2, "helper", "<value>"), (3, "helper", "done")),
            (),
        )
    )
    case: Final = generate(grammar, random.Random(0), force="html:domato:value:2")
    assert parse_fragment(case.data.decode("utf-8")).select("[x]")[0].attrs["x"] == "done"


def test_html_complete_escapes_attribute_literal() -> None:
    grammar: Final = html_grammar_complete(
        HtmlVocabulary(
            ("span",),
            ((1, "attribute_x", 'x="<value>"'),),
            ((1, "value", "<char min=34>&<lt><gt>"),),
            (),
        )
    )
    case: Final = generate(grammar, random.Random(0), force="html:domato:value:1")
    assert (case.data, parse_fragment(case.data.decode("utf-8")).select("[x]")[0].attrs["x"]) == (
        b'<div id="x"><span x="&quot;&amp;&lt;&gt;">x</span><a href="#x">x</a></div>',
        '"&<>',
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("<int>", b"0", id="integer-default"),
        pytest.param("<int min=7 max=9>", b"7", id="integer-minimum"),
        pytest.param("<float min=-1.25 max=2>", b"-1.25", id="float-minimum"),
        pytest.param("<char>", b"x", id="character-default"),
        pytest.param("<string><htmlsafestring><hex>", b"xx0", id="bounded-string"),
        pytest.param("<space><cr><lf>", b" \r\n", id="whitespace"),
    ],
)
def test_html_complete_bounded_primitive_values(source: str, expected: bytes) -> None:
    grammar: Final = html_grammar_complete(
        HtmlVocabulary(
            ("span",),
            ((1, "attribute_x", 'x="<value>"'),),
            ((1, "value", source),),
            (),
        )
    )
    case: Final = generate(grammar, random.Random(0), force="html:domato:value:1")
    assert case.data == b'<div id="x"><span x="' + expected + b'">x</span><a href="#x">x</a></div>'


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        pytest.param(["--count", "0"], "count must be positive", id="zero-count"),
        pytest.param(["--budget", "0"], "budget cannot complete", id="zero-budget"),
    ],
)
def test_html_complete_cli_rejects_invalid_budget(
    arguments: list[str], message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(["--output", str(tmp_path), *arguments])
    assert message in capsys.readouterr().err


def test_html_complete_cli_materializes_bytes(tmp_path: Path) -> None:
    main(["--output", str(tmp_path), "--count", "1", "--budget", "5"])
    assert [path.read_bytes() for path in tmp_path.iterdir()] == [b'<frameset id="x"><frame src="#x"></frameset>']


def test_html_complete_cli_sweep_has_hostile_inputs(tmp_path: Path) -> None:
    main(["--output", str(tmp_path), "--count", "1", "--sweep"])
    assert b'<div id="x"><b><i>x</b>y</i><a href="#x">x</a></div>' in {path.read_bytes() for path in tmp_path.iterdir()}
