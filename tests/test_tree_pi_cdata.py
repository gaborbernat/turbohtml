"""Processing-instruction and CDATA node types: construction, serialization, matching."""

from __future__ import annotations

import pytest

from turbohtml import CData, Comment, Element, ProcessingInstruction, Text


def test_pi_carries_target_and_data() -> None:
    pi = ProcessingInstruction("xml-stylesheet", 'href="a.css"')
    assert pi.target == "xml-stylesheet"
    assert pi.data == 'href="a.css"'
    assert pi.html == '<?xml-stylesheet href="a.css">'
    assert pi.parent is None


def test_pi_with_empty_data() -> None:
    pi = ProcessingInstruction("php", "")
    assert pi.target == "php"
    assert not pi.data
    assert pi.html == "<?php >"


def test_pi_data_is_keyword() -> None:
    assert ProcessingInstruction(target="t", data="d").data == "d"


def test_pi_repr() -> None:
    assert repr(ProcessingInstruction("t", "d")) == "ProcessingInstruction('t', 'd')"


def test_pi_matches_structurally() -> None:
    match ProcessingInstruction("xml", "v=1"):
        case ProcessingInstruction(target, data):
            assert target == "xml"
            assert data == "v=1"
        case _:  # pragma: no cover - a PI always matches
            pytest.fail("did not match")


def test_pi_empty_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="target must not be empty"):
        ProcessingInstruction("", "d")


@pytest.mark.parametrize("target", ["a b", "a>b"])
def test_pi_invalid_target_is_rejected(target: str) -> None:
    with pytest.raises(ValueError, match="invalid character"):
        ProcessingInstruction(target, "d")


def test_pi_target_must_be_str() -> None:
    with pytest.raises(TypeError):
        ProcessingInstruction(1, "d")  # ty: ignore[invalid-argument-type]  # target must be a str


def test_pi_data_must_be_str() -> None:
    with pytest.raises(TypeError):
        ProcessingInstruction("t", 1)  # ty: ignore[invalid-argument-type]  # data must be a str


def test_cdata_carries_data() -> None:
    cdata = CData("x < y & z")
    assert cdata.data == "x < y & z"
    assert cdata.html == "<![CDATA[x < y & z]]>"  # content is verbatim, not escaped
    assert cdata.parent is None


def test_cdata_empty() -> None:
    assert CData("").html == "<![CDATA[]]>"


def test_cdata_repr() -> None:
    assert repr(CData("hi")) == "CData('hi')"


def test_cdata_matches_structurally() -> None:
    match CData("payload"):
        case CData(data):
            assert data == "payload"
        case _:  # pragma: no cover - a CData always matches
            pytest.fail("did not match")


def test_cdata_data_is_settable() -> None:
    cdata = CData("old")
    cdata.data = "new"
    assert cdata.html == "<![CDATA[new]]>"


def test_cdata_data_must_be_str() -> None:
    with pytest.raises(TypeError):
        CData(1)  # ty: ignore[invalid-argument-type]  # data must be a str


def test_pi_and_cdata_embed_in_a_tree() -> None:
    div = Element("div")
    div.extend([Text("a"), ProcessingInstruction("t", "d"), CData("c"), Comment("k")])
    assert div.html == "<div>a<?t d><![CDATA[c]]><!--k--></div>"


def test_pi_adopts_across_trees_keeping_both_halves() -> None:
    pi = ProcessingInstruction("xml", 'version="1.0"')
    box = Element("section")
    box.append(pi)  # a cross-tree adopt must preserve the packed target/data split
    held = box.children[0]
    assert isinstance(held, ProcessingInstruction)
    assert held.target == "xml"
    assert held.data == 'version="1.0"'


def test_pi_and_cdata_serialize_pretty() -> None:
    root = Element("root")
    root.extend([CData("d"), ProcessingInstruction("t", "x")])
    assert root.serialize(indent=2) == "<root>\n  <![CDATA[d]]>\n  <?t x>\n</root>"
