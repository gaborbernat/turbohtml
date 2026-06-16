"""copy.copy / copy.deepcopy duplicate a node's subtree into a standalone tree."""

from __future__ import annotations

import copy

from turbohtml import Element, Text, parse


def test_copy_duplicates_the_subtree() -> None:
    div = parse('<div id="a"><b>x</b>y</div>').find("div")
    assert div is not None
    clone = copy.copy(div)
    assert clone is not div
    assert clone.html == '<div id="a"><b>x</b>y</div>'
    assert clone.parent is None  # the copy is a standalone root


def test_deepcopy_duplicates_the_subtree() -> None:
    div = parse('<div id="a"><b>x</b>y</div>').find("div")
    assert div is not None
    clone = copy.deepcopy(div)
    assert clone.html == '<div id="a"><b>x</b>y</div>'


def test_copy_is_independent_of_the_original() -> None:
    div = parse("<div><b>x</b></div>").find("div")
    assert div is not None
    clone = copy.copy(div)
    clone.append(Element("z"))  # editing the copy must not touch the source
    assert div.html == "<div><b>x</b></div>"
    assert clone.html == "<div><b>x</b><z></z></div>"


def test_copy_of_a_constructed_node() -> None:
    element = Element("p", {"class": ["a", "b"]})
    element.append(Text("hi"))
    assert copy.copy(element).html == '<p class="a b">hi</p>'
