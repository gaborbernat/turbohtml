"""find()/find_all() querying by tag and attributes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import Document, parse

if TYPE_CHECKING:
    from collections.abc import Callable


_DOC = (
    "<body>"
    "<p class=lead id=1>first</p>"
    "<div><p class=lead id=2>nested</p><span data-x=y>s</span></div>"
    "<p id=3>third</p>"
    "</body>"
)


@pytest.fixture
def doc() -> Document:
    return parse(_DOC)


@pytest.mark.parametrize(
    ("tag", "attrs", "first_id"),
    [
        pytest.param("p", {}, "1", id="first-in-document-order"),
        pytest.param("span", {}, None, id="descends-into-subtrees"),
        pytest.param("p", {"id": "3"}, "3", id="by-attribute"),
        pytest.param("table", {}, "__missing__", id="no-match-is-none"),
    ],
)
def test_find(doc: Document, tag: str, attrs: dict[str, str], first_id: str | None) -> None:
    match = doc.find(tag, attrs=attrs)
    if first_id == "__missing__":
        assert match is None
    else:
        assert match is not None
        assert match.attrs.get("id") == first_id


@pytest.mark.parametrize(
    ("tag", "attrs", "ids"),
    [
        pytest.param("p", {}, ["1", "2", "3"], id="tag-only"),
        pytest.param(None, {"class": "lead"}, ["1", "2"], id="attr-only"),
        pytest.param("p", {"class": "lead"}, ["1", "2"], id="tag-and-attr"),
        pytest.param("p", {"id": "2", "class": "lead"}, ["2"], id="two-attrs"),
        pytest.param("p", {"class": "missing"}, [], id="attr-value-mismatch"),
        pytest.param("p", {"role": "x"}, [], id="attr-name-absent"),
    ],
)
def test_find_all(doc: Document, tag: str | None, attrs: dict[str, str], ids: list[str]) -> None:
    assert [m.attrs.get("id") for m in doc.find_all(tag, attrs=attrs)] == ids


def test_find_all_returns_a_list(doc: Document) -> None:
    matches = doc.find_all("p")
    assert isinstance(matches, list)
    assert matches[0].attrs["id"] == "1"


def test_none_tag_matches_any_element() -> None:
    everything = parse("<a><b><c>").find_all(None)
    assert [e.tag for e in everything] == ["html", "head", "body", "a", "b", "c"]


def test_no_argument_matches_the_first_element(doc: Document) -> None:
    match = doc.find()
    assert match is not None
    assert match.tag == "html"


@pytest.mark.parametrize("query", ["find", "find_all"])
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda fn: fn(5), id="non-str-tag"),
        pytest.param(lambda fn: fn("a", "b"), id="extra-positional"),
    ],
)
def test_query_argument_errors(doc: Document, query: str, call: Callable[[Callable[..., object]], object]) -> None:
    with pytest.raises(TypeError):
        call(getattr(doc, query))
