from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse, parse_fragment


@pytest.mark.parametrize("depth", [pytest.param(1, id="shallow"), pytest.param(256, id="deep")])
def test_formatting_reconstruction_keeps_persistent_ancestor(depth: int) -> None:
    source: Final = "<b>" + "<span>" * depth + "<samp>text</samp>" * 100 + "</span>" * depth + "</b>"
    root: Final = parse(source).find("b")
    assert root is not None
    assert (root.text, [element.text for element in root.find_all("samp")]) == ("text" * 100, ["text"] * 100)


@pytest.mark.parametrize("depth", [pytest.param(1, id="shallow"), pytest.param(100, id="deep")])
def test_formatting_reconstruction_after_ancestor_removal(depth: int) -> None:
    source: Final = "<b>" + "<span>" * depth + "first</b>second" + "</span>" * depth + "<i>third</i>"
    root: Final = parse_fragment(source, "div")
    assert (root.text, [element.text for element in root.find_all("b")]) == ("firstsecondthird", ["first"])


@pytest.mark.parametrize(
    ("source", "bold", "italic"),
    [
        pytest.param("<p><b>one</p>two", ["one", "two"], [], id="stack-pop"),
        pytest.param("<b><i>one</b>two</i>", ["one"], ["one", "two"], id="adoption-replacement"),
        pytest.param("<p><b>one</p><div>two</div>three", ["one", "two", "three"], [], id="stack-slot-reuse"),
        pytest.param("<table><tr><td><b>one</td><td>two</td></tr></table>three", ["one"], [], id="cell-marker"),
    ],
)
@pytest.mark.parametrize("locations", [pytest.param(False, id="no-locations"), pytest.param(True, id="locations")])
def test_formatting_reconstruction_stack_changes(
    source: str, bold: list[str], italic: list[str], *, locations: bool
) -> None:
    root: Final = parse_fragment(source, "div", source_locations=locations)
    assert ([element.text for element in root.find_all("b")], [element.text for element in root.find_all("i")]) == (
        bold,
        italic,
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("<p><b><i>one</p>two", [("one", ["one"]), ("two", ["two"])], id="both-formatting-elements-popped"),
        pytest.param("<b><p><i>one</p>two</b>", [("onetwo", ["one", "two"])], id="outer-formatting-element-open"),
        pytest.param("<table><tr><td><p><b>one</p>two", [("one", []), ("two", [])], id="cell-scope-marker"),
    ],
)
def test_formatting_reconstruction_reopens_nested_elements(source: str, expected: list[tuple[str, list[str]]]) -> None:
    root: Final = parse_fragment(source, "div")
    assert [(bold.text, [italic.text for italic in bold.find_all("i")]) for bold in root.find_all("b")] == expected
