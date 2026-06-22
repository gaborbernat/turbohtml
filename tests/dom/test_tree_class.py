"""Element classList edits: has_class membership and add/remove/toggle_class mutation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from turbohtml import Element


@pytest.mark.parametrize(
    ("html", "name", "expected"),
    [
        pytest.param('<div class="a b c">', "b", True, id="present-middle-token"),
        pytest.param('<div class="a b c">', "a", True, id="present-first-token"),
        pytest.param('<div class="a b c">', "c", True, id="present-last-token"),
        pytest.param('<div class="a b c">', "d", False, id="absent-same-length"),
        pytest.param('<div class="a b c">', "ab", False, id="absent-longer"),
        pytest.param('<div class="abc">', "ab", False, id="absent-shorter"),
        pytest.param("<div>", "a", False, id="no-class-attribute"),
        pytest.param("<div class>", "a", False, id="valueless-class"),
        pytest.param('<div class="">', "a", False, id="empty-class"),
        pytest.param('<div class="  a   b  ">', "a", True, id="ignores-surrounding-whitespace"),
        pytest.param('<div class="a b">', "", False, id="empty-name-never-matches"),
        pytest.param('<div class="a b">', "a b", False, id="whitespace-name-never-matches"),
    ],
)
def test_has_class(find: Callable[[str, str], Element], html: str, name: str, *, expected: bool) -> None:
    assert find(html, "div").has_class(name) is expected


@pytest.mark.parametrize(
    ("html", "ops", "expected"),
    [
        pytest.param("<div>", [("add_class", "active")], ["active"], id="add-to-bare-element"),
        pytest.param("<div class>", [("add_class", "active")], ["active"], id="add-to-valueless-class"),
        pytest.param('<div class="a b">', [("add_class", "c")], ["a", "b", "c"], id="add-appends-keeping-order"),
        pytest.param("<div>", [("add_class", "a"), ("add_class", "b")], ["a", "b"], id="add-chains-returning-self"),
        pytest.param('<div class="a b c">', [("remove_class", "b")], ["a", "c"], id="remove-present-token"),
        pytest.param('<div class="a b a c a">', [("remove_class", "a")], ["b", "c"], id="remove-every-occurrence"),
        pytest.param('<div class="a b">', [("remove_class", "a"), ("remove_class", "b")], [], id="remove-chains-empty"),
        pytest.param('<div class="a">', [("toggle_class", "b")], ["a", "b"], id="toggle-adds-when-absent"),
        pytest.param('<div class="a b">', [("toggle_class", "b")], ["a"], id="toggle-removes-when-present"),
        pytest.param("<div>", [("toggle_class", "open")], ["open"], id="toggle-on-bare-element-adds"),
        pytest.param(
            '<div class="a b">', [("toggle_class", "b"), ("toggle_class", "b")], ["a", "b"], id="toggle-twice-restores"
        ),
    ],
)
def test_class_mutation_result(
    find: Callable[[str, str], Element], html: str, ops: list[tuple[str, str]], expected: list[str]
) -> None:
    element = find(html, "div")
    result = element
    for op, name in ops:
        result = getattr(result, op)(name)  # each mutator returns the element, so the calls chain
    assert result is element
    assert element.attrs["class"] == expected


@pytest.mark.parametrize(
    ("html", "op", "name", "expected"),
    [
        # an existing or absent token is a no-op, so the raw value keeps its original whitespace
        pytest.param('<div class="a  b">', "add_class", "a", "a  b", id="add-existing-keeps-raw-value"),
        pytest.param('<div class="a  b">', "remove_class", "c", "a  b", id="remove-absent-keeps-raw-value"),
        # an actual change rewrites the value with single-space separators, collapsing redundant whitespace
        pytest.param('<div class="  a   b  ">', "add_class", "c", "a b c", id="add-collapses-whitespace-on-write"),
    ],
)
def test_class_mutation_raw_value(
    find: Callable[[str, str], Element], html: str, op: str, name: str, expected: str
) -> None:
    assert getattr(find(html, "div"), op)(name).attr("class") == expected


def test_remove_last_token_leaves_empty_class(find: Callable[[str, str], Element]) -> None:
    element = find('<div class="only">', "div")
    element.remove_class("only")
    assert "class" in element.attrs
    assert element.attrs["class"] == []
    assert element.html == '<div class=""></div>'


def test_remove_on_element_without_class_is_a_noop(find: Callable[[str, str], Element]) -> None:
    element = find("<div>", "div")
    element.remove_class("a")
    assert "class" not in element.attrs


@pytest.mark.parametrize("op", ["add_class", "remove_class", "toggle_class"])
@pytest.mark.parametrize(
    ("name", "match"),
    [
        pytest.param("", "class name must not be empty", id="empty"),
        pytest.param("a b", "class name must not contain whitespace", id="whitespace"),
    ],
)
def test_class_mutation_rejects_invalid_name(
    find: Callable[[str, str], Element], op: str, name: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        getattr(find("<div>", "div"), op)(name)


@pytest.mark.parametrize("op", ["has_class", "add_class", "remove_class", "toggle_class"])
def test_class_method_rejects_non_str_name(find: Callable[[str, str], Element], op: str) -> None:
    with pytest.raises(TypeError, match="class name must be a str"):
        getattr(find('<div class="a">', "div"), op)(1)
