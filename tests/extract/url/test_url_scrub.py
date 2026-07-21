"""Conformance tests for the C ``_url_scrub`` behind :func:`turbohtml.extract.clean_url`.

The scrub undoes the HTML transport damage a scraped URL carries before it is split: it strips the leading and trailing
C0-control and space bytes, drops every whitespace character ``str.split()`` would, unwraps a ``<![CDATA[...]]>``
wrapper, truncates at the first ``<``/``>``/``"`` delimiter, undoes a ``&amp;`` escape, and drops a ``&`` dangling after
a ``/``. It replaces the Python strip/split/join, regex split, and replace chain, so the coverage is a differential
against that chain over a generated corpus plus the branch-reaching cases.
"""

from __future__ import annotations

import itertools
import re

import pytest

from turbohtml._html import _url_scrub

_C0_AND_SPACE = "".join(map(chr, range(0x21)))
_MARKUP_DELIMITER = re.compile(r'[<>"]')


def _oracle_scrub(url: str) -> str:
    remainder = "".join(url.strip(_C0_AND_SPACE).split())
    if remainder.startswith("<![CDATA["):
        remainder = remainder.removeprefix("<![CDATA[").removesuffix("]]>")
    remainder = _MARKUP_DELIMITER.split(remainder, maxsplit=1)[0].replace("&amp;", "&")
    return remainder.removesuffix("&") if remainder.endswith("/&") else remainder


# Pieces that reach every scrub branch: whitespace str.split() removes but the edge C0 strip alone would not (NBSP, NEL,
# a separator), a non-whitespace C0 control that survives in the middle, and the CDATA, markup, and escape shapes.
_PIECES = (
    "https://x.example/p",
    " ",
    "\t",
    "\n",
    "\xa0",
    "\x85",
    "\x1c",
    "\x01",
    "<![CDATA[",
    "]]>",
    "<",
    ">",
    '"',
    "&amp;",
    "/&",
    "&",
    "a",
    "//double",
    "?q=1",
    "#f",
)
_EDGE_CASES = (
    "",
    " ",
    "  https://x.example/p  ",
    "\t\nhttps://x.example/p\r\n",
    "\x01\x02https://x.example/p\x03",
    "a\xa0b\x85c",
    "a\x1cb\x1fc",
    "line break",
    "mid\x01control",
    "<![CDATA[https://x.example/p]]>",
    "<![CDATA[https://x.example/p",
    "<![CDATA[a>b",
    "<![CDATA[]]>",
    "<![CDAT",
    "https://x.example/a<script>",
    "https://x.example/a>b",
    'https://x.example/p"junk',
    "https://x.example/a&amp;b&amp;c",
    "https://x.example/path/&amp;",
    "https://x.example/path/&",
    "https://x.example/&amp;",
    "trailing&",
)


def _corpus() -> list[str]:
    seen = set(_EDGE_CASES)
    for length in range(4):
        seen.update("".join(combo) for combo in itertools.product(_PIECES, repeat=length))
    return sorted(seen)


def test_scrub_matches_oracle_over_corpus() -> None:
    for url in _corpus():
        assert _url_scrub(url) == _oracle_scrub(url), repr(url)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param("", "", id="empty"),
        pytest.param("  https://x/p  ", "https://x/p", id="edge-space-stripped"),
        pytest.param("\x01https://x/p\x02", "https://x/p", id="edge-c0-stripped"),
        pytest.param("mid\x01control", "mid\x01control", id="mid-non-ws-c0-kept"),
        pytest.param("a\xa0b", "ab", id="nbsp-whitespace-removed"),
        pytest.param("a b\tc\nd", "abcd", id="internal-whitespace-removed"),
        pytest.param("<![CDATA[https://x/p]]>", "https://x/p", id="cdata-unwrapped"),
        pytest.param("<![CDATA[https://x/p", "https://x/p", id="cdata-open-only"),
        pytest.param("<![CDATA[ab", "ab", id="cdata-content-too-short-for-suffix"),
        pytest.param("<![CDATA[a]x]", "a]x]", id="cdata-suffix-second-char-mismatch"),
        pytest.param("<![CDATA[a]]x", "a]]x", id="cdata-suffix-third-char-mismatch"),
        pytest.param("<![CDAT", "", id="cdata-too-short-truncated-at-lt"),
        pytest.param("https://x/a<b", "https://x/a", id="truncate-at-lt"),
        pytest.param("https://x/a>b", "https://x/a", id="truncate-at-gt"),
        pytest.param('https://x/a"b', "https://x/a", id="truncate-at-quote"),
        pytest.param("https://x/a&amp;b", "https://x/a&b", id="amp-unescaped"),
        pytest.param("https://x/&amp;a&amp;b", "https://x/&a&b", id="amp-unescaped-multiple"),
        pytest.param("https://x/p/&amp;", "https://x/p/", id="trailing-slash-amp-dropped"),
        pytest.param("keep&", "keep&", id="trailing-amp-not-after-slash-kept"),
        pytest.param("a&xzzzz", "a&xzzzz", id="amp-first-char-mismatch"),
        pytest.param("a&abbbb", "a&abbbb", id="amp-second-char-mismatch"),
        pytest.param("a&amxxx", "a&amxxx", id="amp-third-char-mismatch"),
        pytest.param("a&ampxy", "a&ampxy", id="amp-fourth-char-mismatch"),
    ],
)
def test_scrub_cases(url: str, expected: str) -> None:
    assert _url_scrub(url) == expected


def test_scrub_rejects_non_str() -> None:
    with pytest.raises(TypeError, match="must be str"):
        _url_scrub(123)  # ty: ignore[invalid-argument-type]  # a non-str exercises the TypeError guard
