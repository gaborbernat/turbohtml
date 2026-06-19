"""The to_markdown() configuration surface: the markdownify + html2text knobs.

One golden case per option value, plus the binding's validation errors, so every
option code path in the C walker is exercised.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Literal


class _Opts(TypedDict, total=False):
    """The keyword options of Node.to_markdown, so the golden cases stay typed."""

    heading_style: Literal["atx", "atx_closed", "setext"]
    bullets: str
    strong: str
    emphasis: str
    strikethrough: Literal["keep", "hide"]
    ignore_emphasis: bool
    sub_symbol: str
    sup_symbol: str
    code_block_style: Literal["fenced", "indented"]
    code_language: str
    mark_code: bool
    link_style: Literal["inline", "reference"]
    autolink: bool
    link_title: bool
    ignore_links: bool
    skip_internal_links: bool
    base_url: str
    image_mode: Literal["markdown", "alt", "ignore"]
    default_image_alt: str
    table_mode: Literal["markdown", "strip"]
    table_header: Literal["first", "detect", "none"]
    pad_tables: bool
    escape_mode: Literal["minimal", "all"]
    escape_asterisks: bool
    escape_underscores: bool
    line_break: Literal["spaces", "backslash"]
    block_spacing: Literal["double", "single"]
    document_strip: Literal["strip", "lstrip", "rstrip", "none"]
    quote_open: str
    quote_close: str


def md(html: str, opts: _Opts) -> str:
    return parse(html).to_markdown(**opts)


def call_with(convert: Callable[..., str], **kwargs: str | int) -> str:
    """Invoke a converter with options the static signature would reject, to drive
    the runtime validation; the converter arrives signature-erased on purpose."""
    return convert(**kwargs)


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param("<h2>H</h2>", _Opts(heading_style="atx_closed"), "## H ##", id="heading-atx-closed"),
        pytest.param("<h1>H</h1>", _Opts(heading_style="setext"), "H\n=", id="heading-setext-h1"),
        pytest.param("<h2>Hi</h2>", _Opts(heading_style="setext"), "Hi\n--", id="heading-setext-h2"),
        pytest.param("<h3>H</h3>", _Opts(heading_style="setext"), "### H", id="heading-setext-h3-falls-back"),
    ],
)
def test_heading_style(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param("<ul><li>a</li></ul>", _Opts(bullets="*"), "* a", id="bullets-single"),
        pytest.param(
            "<ul><li>a<ul><li>b<ul><li>c</li></ul></li></ul></li></ul>",
            _Opts(bullets="*+"),
            "* a\n  + b\n    * c",
            id="bullets-cycled-by-depth",
        ),
    ],
)
def test_bullets(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param("<p><b>x</b></p>", _Opts(strong="__"), "__x__", id="strong-underscore"),
        pytest.param("<p><em>x</em></p>", _Opts(emphasis="_"), "_x_", id="emphasis-underscore"),
        pytest.param("<p>a<b>x</b><i>y</i><s>z</s>b</p>", _Opts(ignore_emphasis=True), "axyzb", id="ignore-emphasis"),
        pytest.param("<p>a<s>z</s>b</p>", _Opts(strikethrough="hide"), "ab", id="strikethrough-hide"),
        pytest.param("<p>H<sub>2</sub>O</p>", _Opts(sub_symbol="~"), "H~2~O", id="sub-symbol"),
        pytest.param("<p>x<sup>2</sup></p>", _Opts(sup_symbol="^"), "x^2^", id="sup-symbol"),
        pytest.param("<p><q>hi</q></p>", _Opts(quote_open="«", quote_close="»"), "«hi»", id="quote-custom"),
        pytest.param("<p><q>hi</q></p>", _Opts(), '"hi"', id="quote-default"),
    ],
)
def test_inline_markers(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param("<pre><code>x=1</code></pre>", _Opts(code_block_style="indented"), "    x=1", id="code-indented"),
        pytest.param(
            "<pre><code>x=1\ny=2</code></pre>",
            _Opts(code_block_style="indented"),
            "    x=1\n    y=2",
            id="code-indented-multiline",
        ),
        pytest.param("<pre><code>x=1</code></pre>", _Opts(mark_code=True), "[code]\nx=1\n[/code]", id="code-mark"),
        pytest.param(
            "<pre><code>x</code></pre>", _Opts(code_language="py"), "```py\nx\n```", id="code-default-language"
        ),
        pytest.param(
            '<pre><code class="language-c">x</code></pre>',
            _Opts(code_language="py"),
            "```c\nx\n```",
            id="code-language-class-wins",
        ),
    ],
)
def test_code_blocks(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param(
            '<p><a href="http://x">L</a></p>',
            _Opts(link_style="reference"),
            "[L][1]\n\n[1]: http://x",
            id="link-reference",
        ),
        pytest.param(
            '<p><a href="/a" title="T">A</a> <a href="/b">B</a></p>',
            _Opts(link_style="reference"),
            '[A][1] [B][2]\n\n[1]: /a "T"\n[2]: /b',
            id="link-reference-multiple",
        ),
        pytest.param('<p><a href="http://x.com">http://x.com</a></p>', _Opts(), "<http://x.com>", id="autolink-match"),
        pytest.param(
            '<p><a href="http://x.com">text</a></p>',
            _Opts(),
            "[text](http://x.com)",
            id="link-autolink-no-match",
        ),
        pytest.param(
            '<p><a href="http://x.com">http://x.com</a></p>',
            _Opts(autolink=False),
            "[http://x.com](http://x.com)",
            id="link-autolink-disabled",
        ),
        pytest.param('<p><a href="/p">L</a></p>', _Opts(link_title=True), '[L](/p "/p")', id="link-title-from-href"),
        pytest.param('<p><a href="/p">L</a></p>', _Opts(ignore_links=True), "L", id="link-ignore"),
        pytest.param('<p><a href="#sec">L</a></p>', _Opts(skip_internal_links=True), "L", id="link-skip-internal"),
        pytest.param('<p><a href="page">L</a></p>', _Opts(base_url="http://s/"), "[L](http://s/page)", id="link-base"),
        pytest.param(
            '<p><a href="http://x/p">L</a></p>',
            _Opts(base_url="http://s/"),
            "[L](http://x/p)",
            id="link-base-url-absolute-untouched",
        ),
    ],
)
def test_links(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param('<p><img src="i" alt="cat"></p>', _Opts(image_mode="alt"), "cat", id="image-alt"),
        pytest.param('<p>a<img src="i">b</p>', _Opts(image_mode="ignore"), "ab", id="image-ignore"),
        pytest.param('<p><img src="i">b</p>', _Opts(default_image_alt="img"), "![img](i)b", id="image-default-alt"),
        pytest.param(
            '<p><img src="p.png">x</p>', _Opts(base_url="http://s/"), "![](http://s/p.png)x", id="image-base-url"
        ),
    ],
)
def test_images(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param(
            "<table><tr><th>Name</th><th>X</th></tr><tr><td>a</td><td>bb</td></tr></table>",
            _Opts(pad_tables=True),
            "| Name | X   |\n| ---- | --- |\n| a    | bb  |",
            id="table-pad",
        ),
        pytest.param(
            "<table><tr><td>a</td></tr><tr><td>b</td></tr></table>",
            _Opts(pad_tables=True, table_header="none"),
            "|     |\n| --- |\n| a   |\n| b   |",
            id="table-pad-no-header",
        ),
        pytest.param(
            "<table><tr><td>a</td><td>b</td></tr></table>", _Opts(table_mode="strip"), "a b", id="table-strip"
        ),
        pytest.param(
            "<table><tr><td>a</td></tr><tr><td>b</td></tr></table>",
            _Opts(table_header="detect"),
            "|  |\n| --- |\n| a |\n| b |",
            id="table-header-detect-no-header",
        ),
        pytest.param(
            "<table><tr><th>H</th></tr><tr><td>a</td></tr></table>",
            _Opts(table_header="detect"),
            "| H |\n| --- |\n| a |",
            id="table-header-detect-with-th",
        ),
        pytest.param(
            "<table><thead><tr><td>H</td></tr></thead><tbody><tr><td>a</td></tr></tbody></table>",
            _Opts(table_header="detect"),
            "| H |\n| --- |\n| a |",
            id="table-header-detect-thead",
        ),
        pytest.param(
            "<table><tr><!--c--><td>a</td><td>bb</td></tr></table>",
            _Opts(pad_tables=True),
            "| a   | bb  |\n| --- | --- |",
            id="table-pad-comment-in-row",
        ),
        pytest.param(
            "<table><tr><!--c--><td>a</td><td>b</td></tr></table>",
            _Opts(table_mode="strip"),
            "a b",
            id="table-strip-comment-in-row",
        ),
        pytest.param(
            "<table><tr><th>H</th></tr><tr><td>a</td></tr></table>",
            _Opts(table_header="none"),
            "|  |\n| --- |\n| H |\n| a |",
            id="table-header-none",
        ),
    ],
)
def test_tables(html: str, opts: _Opts, expected: str) -> None:
    assert "\n".join(line.rstrip() for line in md(html, opts).splitlines()) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param("<p>a&lt;b&gt;c</p>", _Opts(escape_mode="all"), "a\\<b\\>c", id="escape-all"),
        pytest.param("<p>a*b_c</p>", _Opts(escape_asterisks=False), "a*b\\_c", id="escape-no-asterisks"),
        pytest.param("<p>a*b_c</p>", _Opts(escape_underscores=False), "a\\*b_c", id="escape-no-underscores"),
        pytest.param("<p>a<br>b</p>", _Opts(line_break="backslash"), "a\\\nb", id="break-backslash"),
        pytest.param("<p>a</p><p>b</p>", _Opts(block_spacing="single"), "a\nb", id="spacing-single"),
        pytest.param("  <p>x</p>  ", _Opts(document_strip="none"), "x", id="doc-strip-none"),
        pytest.param("<p>x</p>", _Opts(document_strip="lstrip"), "x", id="doc-strip-lstrip"),
        pytest.param("<p>x</p>", _Opts(document_strip="rstrip"), "x", id="doc-strip-rstrip"),
    ],
)
def test_text_options(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param(
            "<p>&lt; &gt; # + - = ~ | ! &amp;</p>",
            _Opts(escape_mode="all"),
            "\\< \\> \\# \\+ \\- \\= \\~ \\| \\! \\&",
            id="escape-all-every-char",
        ),
        pytest.param('<p><a href="">e</a></p>', _Opts(), "e", id="link-empty-href-dropped"),
        pytest.param(
            '<p><a href="page">L</a></p>', _Opts(skip_internal_links=True), "[L](page)", id="link-skip-non-internal"
        ),
        pytest.param(
            '<p><a href="/abs?q=1">L</a></p>',
            _Opts(base_url="http://s"),
            "[L](http://s/abs?q=1)",
            id="link-base-url-rooted-path",
        ),
        pytest.param(
            '<p><a href="mailto:a@b">L</a></p>',
            _Opts(base_url="http://s/"),
            "[L](mailto:a@b)",
            id="link-base-url-mailto-absolute",
        ),
        pytest.param('<p><img src="/p.png">x</p>', _Opts(base_url="http://s"), "![](http://s/p.png)x", id="image-root"),
        pytest.param(
            '<p><img src="http://x/p">x</p>',
            _Opts(base_url="http://s"),
            "![](http://x/p)x",
            id="image-base-absolute-untouched",
        ),
        pytest.param(
            "<table><tr><!--c--><td>a</td></tr><tr><td>b</td></tr></table>",
            _Opts(table_header="detect"),
            "|  |\n| --- |\n| a |\n| b |",
            id="table-detect-comment-row",
        ),
        pytest.param(
            "<table><tr><th>H</th><td>x</td></tr><tr><td>a</td><td>b</td></tr></table>",
            _Opts(table_mode="strip"),
            "H x\n\na b",
            id="table-strip-with-th",
        ),
    ],
)
def test_option_edge_cases(html: str, opts: _Opts, expected: str) -> None:
    assert "\n".join(line.rstrip() for line in md(html, opts).splitlines()) == expected


@pytest.mark.parametrize(
    ("opts", "exc", "match"),
    [
        pytest.param({"heading_style": "nope"}, ValueError, "heading_style", id="invalid-enum"),
        pytest.param({"bullets": ""}, ValueError, "bullets", id="empty-bullets"),
        pytest.param({"heading_style": 5}, TypeError, "string", id="non-string-enum"),
        pytest.param({"strong": 5}, TypeError, "str", id="wrong-type-marker"),
        pytest.param({"unknown_option": 1}, TypeError, "keyword", id="unknown-keyword"),
    ],
)
def test_invalid_options(opts: Mapping[str, str | int], exc: type[Exception], match: str) -> None:
    with pytest.raises(exc, match=match):
        call_with(parse("<p>x</p>").to_markdown, **opts)


@pytest.mark.parametrize(
    "option",
    [
        "strikethrough",
        "code_block_style",
        "link_style",
        "image_mode",
        "table_mode",
        "table_header",
        "escape_mode",
        "line_break",
        "block_spacing",
        "document_strip",
    ],
)
def test_each_enum_is_validated(option: str) -> None:
    with pytest.raises(ValueError, match=option):
        call_with(parse("<p>x</p>").to_markdown, **{option: "bogus"})


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param(
            '<p><a href="a#b">L</a></p>', _Opts(base_url="http://s/"), "[L](http://s/a#b)", id="abs-hash-relative"
        ),
        pytest.param(
            '<p><a href="q?x">L</a></p>', _Opts(base_url="http://s/"), "[L](http://s/q?x)", id="abs-query-relative"
        ),
        pytest.param('<p><a href="#x">L</a></p>', _Opts(base_url="http://s/"), "[L](#x)", id="base-url-skips-fragment"),
        pytest.param(
            '<p><img src="#x">y</p>', _Opts(base_url="http://s/"), "![](#x)y", id="image-base-url-skips-fragment"
        ),
        pytest.param(
            '<p><a href="http://x.com">http://y.com</a></p>',
            _Opts(),
            "[http://y.com](http://x.com)",
            id="autolink-same-length-no-match",
        ),
    ],
)
def test_href_resolution(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


def test_reference_links_grow_past_initial_capacity() -> None:
    html = "<p>" + "".join(f'<a href="/{i}">L{i}</a>' for i in range(10)) + "</p>"
    out = md(html, _Opts(link_style="reference"))
    assert "[10]: /9" in out


@pytest.mark.parametrize(
    ("opts", "expected"),
    [
        pytest.param(_Opts(pad_tables=True), "| H   | x   |\n| --- | --- |\n| a   | b   |", id="pad-th-and-comment"),
        pytest.param(_Opts(table_mode="strip"), "H x\n\na b", id="strip-th-and-comment"),
    ],
)
def test_table_cells_with_th_and_comment(opts: _Opts, expected: str) -> None:
    html = "<table><tr><!--c--><template></template><th>H</th><td>x</td></tr><tr><td>a</td><td>b</td></tr></table>"
    assert "\n".join(line.rstrip() for line in md(html, opts).splitlines()) == expected
