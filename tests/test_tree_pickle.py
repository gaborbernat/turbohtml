"""Pickling round-trips a node and its subtree, exactly, for every node type."""

from __future__ import annotations

import pickle  # noqa: S403  # round-tripping our own trusted payloads

import pytest

from turbohtml import CData, Comment, Doctype, Document, Element, Node, ProcessingInstruction, Text, parse
from turbohtml._html import _reconstruct  # ty: ignore[unresolved-import]  # the private pickle hook


def _roundtrip(node: Node) -> Node:
    return pickle.loads(pickle.dumps(node))  # noqa: S301  # our own trusted payload


@pytest.mark.parametrize(
    "node",
    [
        Text("a & b <ok>"),
        Comment("a note"),
        CData("x < y & z"),
        ProcessingInstruction("xml-stylesheet", 'href="a.css"'),
        ProcessingInstruction("php", ""),
    ],
    ids=["text", "comment", "cdata", "pi", "pi-empty"],
)
def test_leaf_nodes_round_trip(node: Text | Comment | CData | ProcessingInstruction) -> None:
    clone = _roundtrip(node)
    assert clone is not node
    assert type(clone) is type(node)
    assert clone.html == node.html


def test_element_with_attributes_and_children_round_trips() -> None:
    element = Element("div", {"class": ["card", "lg"], "id": "x", "hidden": None})
    heading = Element("h2")
    heading.text = "Title"
    element.append(heading)
    element.append(Text("tail"))
    clone = _roundtrip(element)
    assert clone.html == '<div class="card lg" id="x" hidden=""><h2>Title</h2>tail</div>'


def test_nested_pi_and_cdata_survive_pickling() -> None:
    # serialize-and-reparse would fold these; pickling carries the child list
    host = Element("host")
    host.append(ProcessingInstruction("t", "d"))
    host.append(CData("raw"))
    assert _roundtrip(host).html == "<host><?t d><![CDATA[raw]]></host>"


def test_document_round_trips() -> None:
    doc = parse("<!DOCTYPE html><title>Hi</title><p id=a>x</p><!--c-->")
    clone = _roundtrip(doc)
    assert isinstance(clone, Document)
    assert clone.html == doc.html


def test_doctype_name_only_round_trips() -> None:
    doctype = parse("<!DOCTYPE html>").children[0]
    assert isinstance(doctype, Doctype)
    clone = _roundtrip(doctype)
    assert isinstance(clone, Doctype)
    assert clone.name == "html"
    assert clone.public_id is None


def test_doctype_with_identifiers_round_trips() -> None:
    markup = '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">'
    doctype = parse(markup).children[0]
    assert isinstance(doctype, Doctype)
    clone = _roundtrip(doctype)
    assert isinstance(clone, Doctype)
    assert clone.public_id == "-//W3C//DTD HTML 4.01//EN"
    assert clone.system_id == "http://www.w3.org/TR/html4/strict.dtd"


def test_pickled_element_is_independent() -> None:
    element = Element("p")
    element.append(Text("x"))
    clone = _roundtrip(element)
    assert isinstance(clone, Element)
    clone.append(Element("b"))  # editing the clone must not touch the original
    assert element.html == "<p>x</p>"
    assert clone.html == "<p>x<b></b></p>"


def test_reconstruct_rejects_malformed_arguments() -> None:
    with pytest.raises(TypeError):
        _reconstruct("not a triple")


def test_reconstruct_propagates_construction_errors() -> None:
    reduced = Element("div").__reduce__()
    assert isinstance(reduced, tuple)
    kind = reduced[1][0]  # the (kind, data, children) payload pickle would store
    with pytest.raises(ValueError, match="invalid character"):
        _reconstruct(kind, ("bad tag", {}), [])  # an invalid tag fails element construction
