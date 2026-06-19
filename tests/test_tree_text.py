"""Layout-aware text export via Node.to_text() (the inscriptis role).

Golden cases pin the layout for every block, list, table, link, and image path,
and a token check confirms no visible text is dropped. A second helper drives the
binding's enum validation.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, TypedDict

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Literal


class _TextOpts(TypedDict, total=False):
    width: int
    links: Literal["none", "inline", "footnote"]
    images: bool
    layout: Literal["extended", "strict"]
    default_image_alt: str
    table_cell_separator: str
    bullet: str


def to_text(html: str, opts: _TextOpts) -> str:
    return parse(html).to_text(**opts)


def call_with(convert: Callable[..., str], **kwargs: str | int) -> str:
    return convert(**kwargs)


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param("<h1>Title</h1><p>Body text.</p>", _TextOpts(), "Title\n\nBody text.", id="heading-and-para"),
        pytest.param("<p>a <b>bold</b> <i>x</i> c</p>", _TextOpts(), "a bold x c", id="inline-markup-stripped"),
        pytest.param("<p>one</p><p>two</p>", _TextOpts(), "one\n\ntwo", id="paragraphs"),
        pytest.param("<div>a\n  b\tc</div>", _TextOpts(), "a b c", id="collapse-whitespace"),
        pytest.param("<p>a<br>b</p>", _TextOpts(), "a\nb", id="line-break"),
        pytest.param("<p>a<wbr>b</p>", _TextOpts(), "ab", id="wbr"),
        pytest.param("<section><p>x</p></section>", _TextOpts(), "x", id="transparent-container"),
        pytest.param("<head><title>t</title></head><body>x</body>", _TextOpts(), "x", id="head-skipped"),
        pytest.param("<p>a</p><script>s()</script><p>b</p>", _TextOpts(), "a\n\nb", id="script-skipped"),
    ],
)
def test_blocks(html: str, opts: _TextOpts, expected: str) -> None:
    assert to_text(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param("<ul><li>one</li><li>two</li></ul>", _TextOpts(), "* one\n* two", id="ul"),
        pytest.param("<ol><li>a</li><li>b</li></ol>", _TextOpts(), "1. a\n2. b", id="ol"),
        pytest.param('<ol start="3"><li>a</li></ol>', _TextOpts(), "3. a", id="ol-start"),
        pytest.param('<ol start="x"><li>a</li></ol>', _TextOpts(), "1. a", id="ol-start-invalid"),
        pytest.param("<ul><li>a<ul><li>b</li></ul></li></ul>", _TextOpts(), "* a\n  * b", id="nested"),
        pytest.param("<ul><li>x</li></ul>", _TextOpts(bullet="- "), "- x", id="custom-bullet"),
        pytest.param("<ul><li> <ul><li>x</li></ul></li></ul>", _TextOpts(), "*\n  * x", id="li-leading-ws"),
        pytest.param("<ul><li></li></ul>", _TextOpts(), "*", id="empty-li"),
    ],
)
def test_lists(html: str, opts: _TextOpts, expected: str) -> None:
    assert "\n".join(line.rstrip() for line in to_text(html, opts).splitlines()) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param(
            "<table><tr><th>Name</th><th>Age</th></tr><tr><td>Alice</td><td>30</td></tr></table>",
            _TextOpts(),
            "Name   Age\nAlice  30",
            id="aligned",
        ),
        pytest.param(
            "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>",
            _TextOpts(),
            "a  b\nc",
            id="ragged",
        ),
        pytest.param(
            "<table><tr><td>a</td><td>b</td></tr></table>",
            _TextOpts(table_cell_separator=" | "),
            "a | b",
            id="custom-separator",
        ),
        pytest.param(
            "<table><tr><!--c--><td>a</td></tr><tr><td>bb</td></tr></table>",
            _TextOpts(),
            "a\nbb",
            id="comment-in-row",
        ),
    ],
)
def test_tables(html: str, opts: _TextOpts, expected: str) -> None:
    assert "\n".join(line.rstrip() for line in to_text(html, opts).splitlines()) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param("<pre>a\n  b</pre>", _TextOpts(), "a\n  b", id="pre-preserved"),
        pytest.param("<pre>x\n</pre>", _TextOpts(), "x", id="pre-trailing-newline"),
        pytest.param(
            "<p>before</p><blockquote><p>quote</p></blockquote>",
            _TextOpts(),
            "before\n\n    quote",
            id="blockquote-indented",
        ),
        pytest.param("<blockquote><p>q</p></blockquote>", _TextOpts(), "    q", id="blockquote-first"),
    ],
)
def test_pre_and_quote(html: str, opts: _TextOpts, expected: str) -> None:
    assert to_text(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param('<p>see <a href="/x">here</a></p>', _TextOpts(), "see here", id="links-none-default"),
        pytest.param(
            '<p>see <a href="http://x">here</a></p>',
            _TextOpts(links="inline"),
            "see here (http://x)",
            id="links-inline",
        ),
        pytest.param(
            '<p><a href="/a">A</a> <a href="/b">B</a></p>',
            _TextOpts(links="footnote"),
            "A[1] B[2]\n\n[1] /a\n[2] /b",
            id="links-footnote",
        ),
        pytest.param("<p><a>no href</a></p>", _TextOpts(links="inline"), "no href", id="link-no-href"),
        pytest.param('<p>a<img src="i" alt="cat">b</p>', _TextOpts(), "ab", id="images-off-default"),
        pytest.param('<p>a <img src="i" alt="cat"> b</p>', _TextOpts(images=True), "a cat b", id="images-alt"),
        pytest.param(
            '<p>a <img src="i"> b</p>',
            _TextOpts(images=True, default_image_alt="img"),
            "a img b",
            id="images-default-alt",
        ),
        pytest.param('<p>a<img src="i">b</p>', _TextOpts(images=True), "ab", id="images-no-alt"),
    ],
)
def test_links_and_images(html: str, opts: _TextOpts, expected: str) -> None:
    assert to_text(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param("<p>a<span>x<!--c-->y</span>b</p>", _TextOpts(), "axyb", id="comment-in-inline"),
        pytest.param("<p>a<span><script>s</script>y</span></p>", _TextOpts(), "ay", id="script-in-inline"),
        pytest.param("<div><span>a<h2>H</h2>b</span></div>", _TextOpts(), "a\n\nHb", id="block-in-inline"),
        pytest.param("<p>a<template>t</template>b</p>", _TextOpts(), "atb", id="template-in-inline"),
        pytest.param("<ul><li><!--c-->x</li></ul>", _TextOpts(), "* x", id="li-leading-comment"),
        pytest.param("<ul><li><script>s</script>x</li></ul>", _TextOpts(), "* x", id="li-leading-script"),
        pytest.param("<div><p>a</p><!--c--><p>b</p></div>", _TextOpts(), "a\n\nb", id="comment-between-blocks"),
        pytest.param('<ol start="2x"><li>a</li></ol>', _TextOpts(), "2. a", id="ol-start-digits-then-letter"),
        pytest.param("<ul><svg></svg><li>a</li></ul>", _TextOpts(), "* a", id="foreign-in-list"),
        pytest.param("<ul><!--c--><li>a</li></ul>", _TextOpts(), "* a", id="comment-in-list"),
        pytest.param("<ul><template></template><li>a</li></ul>", _TextOpts(), "* a", id="non-li-element-in-list"),
        pytest.param("<ul><li><svg></svg>x</li></ul>", _TextOpts(), "* x", id="foreign-leads-li"),
        pytest.param('<ol start="-5"><li>a</li></ol>', _TextOpts(), "1. a", id="ol-negative-start"),
        pytest.param("<p>a<br> b</p>", _TextOpts(), "a\nb", id="break-then-space"),
        pytest.param("<pre></pre>", _TextOpts(), "", id="pre-empty"),
        pytest.param(
            '<p>a <img src="i"> b</p>',
            _TextOpts(images=True, default_image_alt="an img"),
            "a an img b",
            id="alt-spaces",
        ),
    ],
)
def test_text_edge_cases(html: str, opts: _TextOpts, expected: str) -> None:
    assert to_text(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param("<table><tr><td>x<br>y</td></tr><tr><td>z</td></tr></table>", "x y\nz", id="cell-newline"),
        pytest.param("<table><!--c--><tr><td>a</td></tr><tr><td>b</td></tr></table>", "a\nb", id="comment-table-child"),
        pytest.param("<table></table>", "", id="empty-table"),
        pytest.param("<table><tr></tr></table>", "", id="row-no-cells"),
        pytest.param(
            "<table><caption>c</caption><thead><tr><th>H</th></tr></thead>"
            "<tbody><tr><td>a</td></tr></tbody><tfoot><tr><td>f</td></tr></tfoot></table>",
            "H\na\nf",
            id="full-sections",
        ),
        pytest.param("<table><tr><template></template><th>H</th><td>x</td></tr></table>", "H  x", id="th-and-template"),
    ],
)
def test_table_edge_cases(html: str, expected: str) -> None:
    assert "\n".join(line.rstrip() for line in parse(html).to_text().splitlines()) == expected


def test_blockquote_in_tight_item() -> None:
    out = parse("<ul><li>x<blockquote><p>q</p></blockquote></li></ul>").to_text()
    assert out == "* x\n      q"


def test_loose_block_in_tight_item() -> None:
    out = parse("<ul><li>x<table><tr><td>y</td></tr></table></li></ul>").to_text()
    assert out == "* x\n  y"


def test_footnote_links_grow_past_initial_capacity() -> None:
    html = "<p>" + "".join(f'<a href="/{i}">L{i}</a>' for i in range(10)) + "</p>"
    out = parse(html).to_text(links="footnote")
    assert "[10] /9" in out


def test_word_wrap() -> None:
    out = parse("<p>" + "word " * 10 + "</p>").to_text(width=20)
    assert all(len(line) <= 20 for line in out.splitlines())
    assert out.split() == ["word"] * 10


def test_strict_layout_runs() -> None:
    assert parse("<div>a</div><div>b</div>").to_text(layout="strict") == "a\n\nb"


def test_to_text_on_subtree_and_text_node() -> None:
    doc = parse("<article><h2>T</h2><p>body</p></article>")
    article = doc.find("article")
    assert article is not None
    assert article.to_text() == "T\n\nbody"
    para = doc.find("p")
    assert para is not None
    assert para.children[0].to_text() == "body"


def test_to_text_on_foreign_and_template() -> None:
    svg = parse("<p><svg><desc>cap</desc></svg></p>").find("svg")
    assert svg is not None
    assert svg.to_text() == "cap"
    template = parse("<template><p>inside</p></template>").find("template")
    assert template is not None
    assert template.to_text() == "inside"


@pytest.mark.parametrize(
    ("opts", "exc", "match"),
    [
        pytest.param({"links": "nope"}, ValueError, "links", id="invalid-links"),
        pytest.param({"layout": "nope"}, ValueError, "layout", id="invalid-layout"),
        pytest.param({"links": 5}, TypeError, "string", id="non-string-enum"),
        pytest.param({"width": "x"}, TypeError, "int", id="wrong-type-width"),
        pytest.param({"bogus": 1}, TypeError, "keyword", id="unknown-keyword"),
    ],
)
def test_invalid_options(opts: Mapping[str, str | int], exc: type[Exception], match: str) -> None:
    with pytest.raises(exc, match=match):
        call_with(parse("<p>x</p>").to_text, **opts)


_WORD = re.compile(r"[0-9a-z]+")


@pytest.mark.parametrize(
    "html",
    [
        pytest.param("<h1>Hello World</h1><p>Some text with <b>bold</b> bits.</p>", id="article"),
        pytest.param("<ul><li>apple</li><li>banana</li></ul>", id="list"),
        pytest.param("<table><tr><th>Name</th><th>Age</th></tr><tr><td>Alice</td><td>30</td></tr></table>", id="table"),
        pytest.param("<blockquote><p>a quote here</p></blockquote><p>and more</p>", id="quote"),
    ],
)
def test_no_visible_text_lost(html: str) -> None:
    source = _WORD.findall(" ".join(parse(html).stripped_strings).lower())
    rendered = _WORD.findall(parse(html).to_text().lower())
    assert rendered == source
