"""parse_xml() cross-checked against lxml.

lxml is a bench dependency, not a test one, and ships no wheels for 3.15, the free-threaded builds, or Windows, so this
module importorskips itself where the oracle is absent and is omitted from the coverage gate (see ``[tool.coverage]``).
It still runs and validates wherever lxml installs.
"""

from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml import Document, Element, parse_xml


def elements(node: Element) -> list[Element]:
    return [child for child in node if isinstance(child, Element)]


def root_of(doc: Document) -> Element:
    root = doc.children[0]
    assert isinstance(root, Element)
    return root


def localnames(node: Element) -> list[str]:
    out = [node.tag.split(":")[-1]]
    for child in elements(node):
        out.extend(localnames(child))
    return out


def test_round_trip_against_lxml() -> None:
    lxml_etree = pytest.importorskip("lxml.etree")
    source = (
        '<catalog xmlns:dc="urn:dc">'
        '<book id="b1"><dc:title>One</dc:title><price>9.99</price></book>'
        '<book id="b2"><dc:title>Two &amp; a half</dc:title><price>5.00</price></book>'
        "<!-- end --></catalog>"
    )
    theirs = lxml_etree.fromstring(source.encode())
    ours = root_of(parse_xml(source))
    their_locals = [lxml_etree.QName(node).localname for node in theirs.iter() if isinstance(node.tag, str)]
    assert localnames(ours) == their_locals


@pytest.mark.parametrize(("index", "count"), [(0, 128), (1, 1)], ids=["many", "single"])
def test_lxml_namespace_benchmark_output(index: int, count: int) -> None:
    etree: Final = pytest.importorskip("lxml.etree", exc_type=ImportError)
    root: Final = etree.fromstring(cast("str", INPUTS["parse-xml-prefixes"]()[index][1]).encode())
    assert (root.tag, list(root.nsmap.items()), list(root.attrib.items()), len(root)) == (
        "root",
        [(f"p{number}", f"urn:{number}") for number in range(count)],
        [(f"{{urn:{number}}}value", "x") for number in range(count)],
        0,
    )


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, "a" * 65536), (1, "a&b " * 8192), (2, "hello")],
    ids=["clean", "references", "tiny"],
)
def test_lxml_text_benchmark_output(index: int, expected: str) -> None:
    etree: Final = pytest.importorskip("lxml.etree", exc_type=ImportError)
    root: Final = etree.fromstring(cast("str", INPUTS["parse-xml-text"]()[index][1]).encode())
    assert (root.tag, root.text, len(root)) == ("root", expected, 0)
