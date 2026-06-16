"""Constructing standalone Text and Comment nodes."""

from __future__ import annotations

import pytest

from turbohtml import Comment, Text


def test_text_carries_its_data() -> None:
    text = Text("a & b")
    assert text.data == "a & b"
    assert text.parent is None  # a freshly built node has no parent yet


def test_text_serializes_escaped() -> None:
    assert Text("Tom & Jerry <ok>").html == "Tom &amp; Jerry &lt;ok&gt;"


def test_comment_carries_its_data_and_serializes() -> None:
    comment = Comment("a note")
    assert comment.data == "a note"
    assert comment.html == "<!--a note-->"


def test_empty_nodes() -> None:
    assert not Text("").data  # empty data round-trips as the empty string
    assert not Text("").html
    assert Comment("").html == "<!---->"


def test_data_is_keyword() -> None:
    assert Text(data="x").data == "x"
    assert Comment(data="x").data == "x"


def test_constructed_node_matches_structurally() -> None:
    match Text("hi"):
        case Text(data):
            assert data == "hi"
        case _:  # pragma: no cover - a Text always matches Text
            pytest.fail("did not match")


@pytest.mark.parametrize("node_type", [Text, Comment])
def test_data_must_be_a_str(node_type: type[Text | Comment]) -> None:
    with pytest.raises(TypeError):
        node_type(123)  # ty: ignore[invalid-argument-type]  # data must be a str
