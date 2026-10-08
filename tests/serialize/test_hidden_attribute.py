"""The hidden attribute hides an element from to_markdown and to_text (WHATWG Rendering 15.3.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import Element, Text, parse, parse_xml

if TYPE_CHECKING:
    from collections.abc import Callable

    from turbohtml import Node


def _set_after_parse() -> Node:
    document = parse("<p>a</p><p>h</p>")
    document.select("p")[1].attrs["hidden"] = ""
    return document


def _built() -> Node:
    return Element("div", children=[Element("p", children=[Text("a")]), Element("p", {"hidden": ""}, [Text("h")])])


def _imported() -> Node:
    document = parse("<div><p>a</p></div>")
    document.select_one("div").append(parse("<p hidden>h</p>").select_one("p"))
    return document


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        pytest.param(lambda: parse("<p>a</p><p hidden>h</p>"), "a", id="parsed"),
        pytest.param(lambda: parse("<p>a</p><body hidden>"), "", id="merged-into-body"),
        pytest.param(_set_after_parse, "a", id="set-after-parse"),
        pytest.param(_built, "a", id="built"),
        pytest.param(
            lambda: parse_xml('<div xmlns="http://www.w3.org/1999/xhtml"><p>a</p><p hidden="">h</p></div>'),
            "a",
            id="xml",
        ),
        pytest.param(_imported, "a", id="imported-from-another-tree"),
    ],
)
def test_hidden_attribute_hides_from_markdown(build: Callable[[], Node], expected: str) -> None:
    assert build().to_markdown() == expected


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        pytest.param("<p>a<span hidden=until-found>u</span>b</p>", "aub", id="until-found-kept"),
        pytest.param("<p>a<span hidden=UNTIL-FOUND>u</span>b</p>", "aub", id="until-found-any-case-kept"),
        pytest.param("<p>a<span hidden=until-founds>u</span>b</p>", "ab", id="other-value-hidden"),
        pytest.param("<p>a<svg><text hidden>s</text></svg>b</p>", "asb", id="svg-element-kept"),
    ],
)
def test_hidden_attribute_value_and_namespace(markup: str, expected: str) -> None:
    assert parse(markup).to_markdown() == expected


def test_hidden_attribute_hides_from_text() -> None:
    assert parse("<p>a</p><p hidden>h</p><p>b</p>").to_text() == "a\n\nb"


def test_hidden_attribute_hides_from_annotated_text() -> None:
    assert parse("<p>a</p><p hidden>h</p><p>b</p>").to_annotated_text({"p": ["p"]}) == (
        "a\n\nb",
        [(0, 1, "p"), (3, 4, "p")],
    )
