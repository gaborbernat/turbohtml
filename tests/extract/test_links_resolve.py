from __future__ import annotations

from html import escape
from urllib.parse import urljoin

import pytest

from turbohtml import parse, parse_fragment

_BASE = "https://example.com/dir/page.html"
_HTTPS = "https://example.com/dir/"


def _resolved(html: str, base: str = _BASE) -> str:
    root = parse_fragment(html)
    root.resolve_links(base)
    return root.inner_html


def test_relative_href_becomes_absolute() -> None:
    assert _resolved('<a href="a/b.html">x</a>') == '<a href="https://example.com/dir/a/b.html">x</a>'


def test_root_relative_href_resolves_against_origin() -> None:
    assert _resolved('<a href="/top.html">x</a>') == '<a href="https://example.com/top.html">x</a>'


def test_absolute_href_is_left_unchanged() -> None:
    assert _resolved('<a href="https://other.test/x">y</a>') == '<a href="https://other.test/x">y</a>'


def test_fragment_only_href_resolves_against_the_page() -> None:
    assert _resolved('<a href="#sec">y</a>') == '<a href="https://example.com/dir/page.html#sec">y</a>'


def test_srcset_candidates_are_each_resolved() -> None:
    out = _resolved('<img srcset="a.png 1x, b.png 2x">')
    assert out == '<img srcset="https://example.com/dir/a.png 1x, https://example.com/dir/b.png 2x">'


def test_ping_list_entries_are_each_resolved() -> None:
    out = _resolved('<a href="h" ping="p1 p2">x</a>')
    assert 'ping="https://example.com/dir/p1 https://example.com/dir/p2"' in out


def test_css_url_in_style_attribute_is_resolved() -> None:
    out = _resolved('<p style="background:url(bg.png)"></p>')
    assert out == '<p style="background:url(https://example.com/dir/bg.png)"></p>'


def test_css_url_in_style_element_is_resolved() -> None:
    root = parse_fragment("<style>a{background:url(bg.png)} @import 'theme.css';</style>")
    root.resolve_links(_BASE)
    assert root.inner_html == (
        "<style>a{background:url(https://example.com/dir/bg.png)} @import 'https://example.com/dir/theme.css';</style>"
    )


def test_meta_refresh_url_is_resolved() -> None:
    out = _resolved('<meta http-equiv="refresh" content="5; url=next.html">')
    assert out == '<meta http-equiv="refresh" content="5; url=https://example.com/dir/next.html">'


def test_resolve_on_a_whole_document_returns_none() -> None:
    doc = parse('<html><body><a href="a.html">x</a></body></html>')
    assert doc.resolve_links(_BASE) is None
    (link,) = doc.links()
    assert link.url == "https://example.com/dir/a.html"


def test_a_longer_replacement_grows_the_value() -> None:
    out = _resolved('<a href="x">t</a>', "https://example.com/very/deep/path/")
    assert out == '<a href="https://example.com/very/deep/path/x">t</a>'


@pytest.mark.parametrize(
    "html",
    [
        pytest.param('<a href="">x</a>', id="empty-href"),
        pytest.param("<style></style>", id="empty-style"),
        pytest.param('<meta http-equiv="refresh" content="5">', id="refresh-no-url"),
    ],
)
def test_nothing_to_resolve_is_a_no_op(html: str) -> None:
    assert _resolved(html) == html


def test_resolve_links_requires_a_string_base() -> None:
    with pytest.raises(TypeError, match="base URL string"):
        parse_fragment('<a href="a">x</a>').resolve_links(None)  # ty: ignore[invalid-argument-type]


def _resolved_href(href: str, base: str) -> str:
    root = parse_fragment(f'<a href="{escape(href, quote=True)}">x</a>')
    root.resolve_links(base)
    (link,) = root.links()
    return link.url


# resolve_links skips urljoin for an already-absolute link it would return unchanged; every case must still match the
# stdlib join it stands in for, whether the link is skipped (absolute) or rejoined (relative, or a would-be
# skip that urljoin rewrites). The href carries no surrounding whitespace, so the scanned span is the whole value.
@pytest.mark.parametrize(
    ("base", "href"),
    [
        pytest.param(_HTTPS, "https://host/p?q#f", id="same-scheme-absolute-skipped"),
        pytest.param(_HTTPS, "https://user:pw@host:8080/a;b?q#f", id="same-scheme-userinfo-port"),
        pytest.param(_HTTPS, "https://HOST.example/Path", id="same-scheme-host-case-preserved"),
        pytest.param(_HTTPS, "https://host/a/../b", id="same-scheme-dot-segments-preserved"),
        pytest.param(_HTTPS, "http://host/p", id="different-scheme-http"),
        pytest.param(_HTTPS, "mailto:a@b.test", id="different-scheme-not-relative"),
        pytest.param(_HTTPS, "data:text/plain,hi", id="different-scheme-data"),
        pytest.param(_HTTPS, "wsabc://host", id="same-length-different-scheme"),
        pytest.param(_HTTPS, "HTTPS://host/p", id="same-scheme-uppercase-rejoined"),
        pytest.param(_HTTPS, "HtTpS://host/p", id="same-scheme-mixed-case-rejoined"),
        pytest.param(_HTTPS, "https:/one-slash", id="same-scheme-single-slash-rejoined"),
        pytest.param(_HTTPS, "https:opaque", id="same-scheme-no-slashes-rejoined"),
        pytest.param(_HTTPS, "https:", id="same-scheme-bare-rejoined"),
        pytest.param(_HTTPS, "https://", id="same-scheme-empty-authority-rejoined"),
        pytest.param(_HTTPS, "https:///path", id="same-scheme-empty-authority-slash-rejoined"),
        pytest.param(_HTTPS, "https://?q", id="same-scheme-empty-authority-query-rejoined"),
        pytest.param(_HTTPS, "https://#f", id="same-scheme-empty-authority-fragment-rejoined"),
        pytest.param(_HTTPS, "/root", id="relative-root"),
        pytest.param(_HTTPS, "#frag", id="relative-fragment"),
        pytest.param(_HTTPS, "?query", id="relative-query"),
        pytest.param(_HTTPS, "path/to.html", id="relative-path-with-slash"),
        pytest.param(_HTTPS, "bareword", id="relative-bareword-no-colon"),
        pytest.param(_HTTPS, "s3://bucket/key", id="scheme-with-digit"),
        pytest.param(_HTTPS, "a+b://host", id="scheme-with-plus"),
        pytest.param(_HTTPS, "a-b://host", id="scheme-with-hyphen"),
        pytest.param(_HTTPS, "a.b://host", id="scheme-with-dot"),
        pytest.param("http://ex.test/a/b", "http://other.test/x", id="http-base-same-scheme"),
        pytest.param("ftp://f.test/g/", "ftp://h.test/x", id="netloc-base-not-http-not-skipped"),
        pytest.param("s3://n.test/", "s3://m.test/x", id="base-scheme-with-digit"),
        pytest.param("a+b://n.test/", "a+b://m.test/x", id="base-scheme-with-plus"),
        pytest.param("a-b://n.test/", "a-b://m.test/x", id="base-scheme-with-hyphen"),
        pytest.param("a.b://n.test/", "a.b://m.test/x", id="base-scheme-with-dot"),
        pytest.param("abcde://n.test/", "abcde://m.test/x", id="five-char-base-scheme-not-https"),
        pytest.param("news://n.test/", "news://m.test/x", id="four-char-base-scheme-not-http"),
        pytest.param("", "https://host/x", id="empty-base-absolute"),
        pytest.param("", "relative/x", id="empty-base-relative"),
        pytest.param("/no-scheme/base", "https://host/x", id="schemeless-base"),
        pytest.param("http", "https://host/x", id="base-scheme-without-colon"),
        pytest.param("ht tp://x/", "https://host/x", id="base-scheme-invalid-char"),
        pytest.param("abcdefghijklmnop://h/", "abcdefghijklmnop://y", id="base-scheme-too-long"),
    ],
)
def test_resolve_matches_urljoin(base: str, href: str) -> None:
    assert _resolved_href(href, base) == urljoin(base, href)


# A tab/CR/LF inside an otherwise-skippable absolute link forces the rejoin urlsplit would strip it in; a character
# reference carries the raw control byte past the input stream's CR/LF normalization so each lands in the value.
@pytest.mark.parametrize(
    ("reference", "char"),
    [
        pytest.param("&#9;", "\t", id="tab"),
        pytest.param("&#13;", "\r", id="carriage-return"),
        pytest.param("&#10;", "\n", id="line-feed"),
    ],
)
def test_same_scheme_absolute_with_internal_control_char_is_rejoined(reference: str, char: str) -> None:
    root = parse_fragment(f'<a href="https://host/a{reference}b">x</a>')
    root.resolve_links(_HTTPS)
    (link,) = root.links()
    assert link.url == urljoin(_HTTPS, f"https://host/a{char}b")
