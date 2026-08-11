"""Round-trip safety of serialize(layout=Minify(...)) over an adversarial corpus.

Minification is only correct if the minified bytes reparse to the same tree. This
suite enforces that property at scale against WPT's tree-construction
suite -- 1.9k adversarial snippets from the committed WPT corpus, already
in place for the conformance harness.

The check is idempotence under reparse: ``minify(parse(minify(parse(src))))`` must
equal ``minify(parse(src))``. A tag omission or whitespace fold that changed the
tree would shift the second pass. Pathological adoption-agency inputs are not
idempotent even under the plain serializer (``<a><a>`` reparses to siblings), so
those cases are measured against the plain-serializer baseline and only count when
the plain serializer itself round-trips.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import Html, Minify, parse
from turbohtml.clean import CSSMinify

if TYPE_CHECKING:
    from wpt_tree_corpus import WptHtmlTreeCorpus


def _plain_roundtrips(source: str) -> bool:
    once = parse(source).serialize()
    return once == parse(once).serialize()


def _minify_idempotent(source: str, layout: Minify) -> bool:
    once = parse(source).serialize(Html(layout=layout))
    return once == parse(once).serialize(Html(layout=layout))


@pytest.mark.parametrize(
    "layout",
    [pytest.param(Minify(), id="default"), pytest.param(Minify(minify_css=CSSMinify()), id="minify-css")],
)
def test_minify_idempotent_over_tree_construction(wpt_html_tree_corpus: WptHtmlTreeCorpus, layout: Minify) -> None:
    # only the subset the plain serializer round-trips can be asked of the minifier;
    # the rest are inherently non-idempotent adoption-agency reconstructions
    failures = [
        f"{case['file']}: {data!r}\n  once:    {parse(data).serialize(Html(layout=layout))!r}\n"
        f"  reparse: {parse(parse(data).serialize(Html(layout=layout))).serialize(Html(layout=layout))!r}"
        for case in wpt_html_tree_corpus["cases"]
        if case["context"] is None and case["scripting"] is not True
        for data in [case["data"]]
        if _plain_roundtrips(data) and not _minify_idempotent(data, layout)
    ]
    assert not failures, f"{len(failures)} non-idempotent\n\n" + "\n\n".join(failures[:5])


def test_minify_idempotent_over_large_document() -> None:
    # a large well-formed document exercises every transform at scale (whitespace,
    # optional tags, attribute unquoting, comment stripping) past the serialization
    # buffer's growth, where the per-snippet suite stays small
    section = (
        "<section id='s{i}'>\n"
        "  <h2>Heading {i} &amp; more</h2>\n"
        "  <p class='lead'>Some   prose with    spaces and a <a href='/x{i}'>link</a> here.</p>\n"
        "  <ul>\n    <li>one</li>\n    <li>two</li>\n  </ul>\n"
        "  <!-- note {i} -->\n"
        "  <table><tbody><tr><td>a</td><td>b</td></tr></tbody></table>\n"
        "</section>\n"
    )
    big = (
        "<!doctype html><html><head><title>Big</title></head><body>\n"
        + "".join(section.format(i=index) for index in range(500))
        + "</body></html>"
    )
    layout = Minify()
    once = parse(big).serialize(Html(layout=layout))
    assert once == parse(once).serialize(Html(layout=layout))
    assert len(once) < len(parse(big).serialize())  # minification actually shrinks the document
