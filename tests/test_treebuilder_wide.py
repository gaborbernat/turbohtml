"""Tree-builder coverage for non-1-byte input and the bulk fast paths.

The html5lib tree-construction suite is almost entirely ASCII, so it never
drives the UCS-2 / UCS-4 storage widths nor the vectorized run-scans those
widths use. These tests feed wide content long enough to enter the SIMD block
loops (>= 8 UCS-2 / >= 4 UCS-4 code points per run) and exercise the width
dispatch in text, name, comment, and attribute-value materialization.
"""

from __future__ import annotations

import pytest

from turbohtml import _html

# eight+ BMP (UCS-2) code points and four+ astral (UCS-4) code points, so a run
# of them is long enough to reach the vector block loop and leave a scalar tail
CJK = "東京都港区六本木ヒルズ森タワー"  # UCS-2
EMOJI = "😀🎉🚀🐍🌟🔥💡"  # UCS-4


def _body_text(html: str) -> str:
    """The serialized document tree for a whole-document parse."""
    return _html._parse_tree(html).rstrip("\n")


@pytest.mark.parametrize(
    ("html", "needle"),
    [
        pytest.param(f"<p>{CJK}</p>", f'"{CJK}"', id="ucs2-text-run"),
        pytest.param(f"<p>{EMOJI}</p>", f'"{EMOJI}"', id="ucs4-text-run"),
        pytest.param(f"<p>{CJK}&amp;{CJK}</p>", f'"{CJK}&{CJK}"', id="ucs2-text-with-ref"),
        pytest.param(f"<!--{CJK}-->", f"<!-- {CJK} -->", id="ucs2-comment"),
        pytest.param(f"<!--{EMOJI}-->", f"<!-- {EMOJI} -->", id="ucs4-comment"),
        pytest.param(f'<p title="{CJK}{EMOJI}">x</p>', f'title="{CJK}{EMOJI}"', id="double-quoted-attr"),
        # single quotes serialize back as double quotes
        pytest.param(f"<p title='{EMOJI}{CJK}'>x</p>", f'title="{EMOJI}{CJK}"', id="single-quoted-attr"),
        # an ASCII-led name carrying wide chars is a non-1-byte buffer, so it never interns to a
        # known atom and stays a plain element (a bare "<東" is not a tag - names must open ASCII)
        pytest.param(f"<a{CJK}>x</a{CJK}>", f"<a{CJK}>", id="non-ascii-tag-name"),
        # title is RCDATA, style is RAWTEXT; both take the wide run-scan
        pytest.param(f"<title>{CJK}{EMOJI}</title>", CJK, id="rcdata-wide-run"),
        pytest.param(f"<style>{EMOJI}{CJK}</style>", EMOJI, id="rawtext-wide-run"),
        # plaintext consumes the rest of the input through the wide run-scan
        pytest.param(f"<plaintext>{CJK}{EMOJI}", f"{CJK}{EMOJI}", id="plaintext-wide-run"),
    ],
)
def test_wide_character_data(html: str, needle: str) -> None:
    assert needle in _body_text(html)


@pytest.mark.parametrize(
    ("html", "present", "absent"),
    [
        # a non-1-byte attribute name takes the per-character copy path; the element and value
        # still parse and the trailing text lands in the body
        pytest.param(f'<p {CJK}="1">x</p>', ['="1"', '"x"'], [], id="non-ascii-attr-name"),
        # a CR in wide input forces the copy-and-normalize path; the CR becomes LF
        pytest.param(f"<pre>{CJK}\r\n{EMOJI}</pre>", [CJK], ["\r"], id="wide-carriage-return"),
        # a NUL in wide input sets the document NUL flag and is dropped from text
        pytest.param(f"<p>{CJK}\x00{EMOJI}</p>", [f"{CJK}{EMOJI}"], ["\x00"], id="wide-nul"),
    ],
)
def test_wide_present_and_absent(html: str, present: list[str], absent: list[str]) -> None:
    out = _body_text(html)
    assert all(needle in out for needle in present)
    assert all(needle not in out for needle in absent)
