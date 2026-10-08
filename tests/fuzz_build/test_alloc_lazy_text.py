from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Final

import pytest

import turbohtml
from turbohtml import Html, Indent, Markdown, Minify, Range
from turbohtml.clean import Linker, Linkify, Policy, Sanitizer, linkify_node

if TYPE_CHECKING:
    from collections.abc import Callable

# Parsed text nodes keep a zero-copy span of the input until a reader needs an owned copy. Each run parses afresh, so
# every reader below meets unrealized spans: a raw-text style and pre, adjacent text runs, commas, whitespace-only
# text, and table cells, which text and Markdown render into buffers of their own. The fuzz build grows the tree arena
# from one slot, doubling each block, so a short span realizes into room left over from parsing. A long span needs a
# block of its own, which the sweep then fails; the code span is four times longer than the paragraph's, so it outgrows
# the block the paragraph's realization opened, and the text around the long paragraph's link outgrows it the same way.
_LONG: Final[str] = "word " * 1200
_MARKUP: Final[str] = (
    "<!DOCTYPE html><style>p { color: red }</style><pre>\nkeep</pre>"
    f"<p>one, two <b>three</b>\u00e9 {_LONG}</p><code><div>x</div>{_LONG * 4}</code>"
    "<p> </p><div>  </div><p>see https://example.com now</p>"
    f"<p>{_LONG}https://example.net {_LONG}</p><p dir=auto>\u05d0 <a href=/x>https://example.org</a></p>"
    "<table><tr><td>cell, text</td><td><b>bold</b> cell</td></tr></table>"
)
_SANITIZER: Final[Sanitizer] = Sanitizer(Policy.strict())
_EXISTING_LINKER: Final[Linker] = Linker(Linkify(process_existing=True))


def _document() -> turbohtml.Document:
    return turbohtml.parse(_MARKUP)


def _paragraph(document: turbohtml.Document) -> turbohtml.Element:
    paragraph = document.select_one("p")
    assert paragraph is not None
    return paragraph


def _long_text(document: turbohtml.Document) -> turbohtml.Text:
    text = _paragraph(document).children[-1]
    assert isinstance(text, turbohtml.Text)
    return text


def _range_delete(document: turbohtml.Document) -> None:
    text = _long_text(document)
    text_range = Range(text, 1)
    text_range.set_end(text, len(_LONG))
    text_range.delete_contents()


def _normalize(document: turbohtml.Document) -> None:
    paragraph = _paragraph(document)
    paragraph.append(turbohtml.parse_fragment("more").children[0])
    paragraph.normalize()


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda document: document.serialize(), id="serialize"),
        pytest.param(lambda document: document.serialize(Html(layout=Indent())), id="indent"),
        pytest.param(lambda document: document.serialize(Html(layout=Minify())), id="minify"),
        pytest.param(lambda document: document.inner_html, id="inner-html"),
        pytest.param(lambda document: document.canonicalize(), id="canonicalize"),
        pytest.param(lambda document: document.to_markdown(), id="markdown"),
        pytest.param(
            lambda document: document.to_markdown(Markdown(tables=Markdown.Tables(pad=True))), id="markdown-padded"
        ),
        pytest.param(lambda document: document.to_text(), id="text"),
        pytest.param(lambda document: document.text, id="text-content"),
        pytest.param(lambda document: _long_text(document).data, id="data"),
        pytest.param(lambda document: document.select("p:empty"), id="empty-selector"),
        pytest.param(lambda document: document.select(":dir(rtl)"), id="dir-selector"),
        pytest.param(linkify_node, id="linkify"),
        pytest.param(_EXISTING_LINKER.linkify_node, id="linkify-existing"),
        pytest.param(lambda document: document.equals(copy.copy(document)), id="equals"),
        pytest.param(_SANITIZER.sanitize_node, id="sanitize"),
        pytest.param(_range_delete, id="range-delete"),
        pytest.param(_normalize, id="normalize"),
        pytest.param(lambda document: setattr(_long_text(document), "data", "x"), id="set-data"),
    ],
)
def test_lazy_text_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], call: Callable[[turbohtml.Document], object]
) -> None:
    assert set(alloc_sweep(call, _document)) == {"MemoryError"}


def test_lazy_text_failed_realization_keeps_the_text(alloc_sweep: Callable[..., list[str]]) -> None:
    documents: list[turbohtml.Document] = []

    def setup() -> turbohtml.Document:
        documents.append(_document())
        return documents[-1]

    alloc_sweep(lambda document: document.to_markdown(), setup)
    assert {_long_text(document).data for document in documents} == {f"\u00e9 {_LONG}"}
