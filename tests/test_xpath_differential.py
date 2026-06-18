"""Differential validation of the XPath engine against lxml (libxml2).

lxml is the libxml2-backed XPath 1.0 oracle that lxml/parsel/pyquery/html5-parser all
wrap, so the same expression over the same well-formed document must select the same
nodes in the same order. Node-sets are compared by element tag (and by the exact string
for attribute/text results); both engines parse these fixtures to the same tree.

Only the Phase-2 subset (location paths, no predicates/functions/operators) is exercised.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import turbohtml

lxml_html = pytest.importorskip("lxml.html")

if TYPE_CHECKING:
    from collections.abc import Iterable

DOCS = {
    "article": (
        "<!doctype html><html><head><title>T</title></head><body>"
        '<main><article id="a1"><h2>One</h2><p>p1</p><p class="lead">p2</p></article>'
        '<article id="a2"><h2>Two</h2><p>p3</p></article></main>'
        '<nav><ul><li><a href="/x">x</a></li><li><a href="/y">y</a></li></ul></nav>'
        "</body></html>"
    ),
    "table": (
        "<!doctype html><html><head></head><body><table><thead>"
        "<tr><th>H1</th><th>H2</th></tr></thead><tbody>"
        "<tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr>"
        "</tbody></table></body></html>"
    ),
}

EXPRS = [
    "//p",
    "//a",
    "//a/@href",
    "//p/text()",
    "//h2/text()",
    "/html/body//p",
    "//article",
    "//article/p",
    "//article/h2",
    "//main/article",
    "//*",
    "//div//span",
    "//nav//a/@href",
    "//td",
    "//tr/td",
    "//table//th/text()",
    "//thead/tr/th",
    "descendant::li",
    "//ul/li/a",
    "/html/head/title/text()",
    "//body/*",
]


def normalize(result: Iterable[object]) -> list[str]:
    out: list[str] = []
    for item in result:
        if isinstance(item, str):
            out.append(item)
        else:
            tag = getattr(item, "tag", None)  # both engines expose .tag on elements
            out.append(tag if isinstance(tag, str) else f"<{type(item).__name__}>")
    return out


@pytest.mark.parametrize("expr", EXPRS, ids=lambda e: e)
@pytest.mark.parametrize("doc_name", list(DOCS), ids=list(DOCS))
def test_matches_lxml(doc_name: str, expr: str) -> None:
    html = DOCS[doc_name]
    ours = normalize(turbohtml.parse(html).xpath(expr))
    theirs = normalize(lxml_html.document_fromstring(html).xpath(expr))
    assert ours == theirs
