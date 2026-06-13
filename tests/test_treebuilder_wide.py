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
    ],
)
def test_wide_character_data(html: str, needle: str) -> None:
    assert needle in _body_text(html)


def test_wide_double_quoted_attribute_value() -> None:
    out = _body_text(f'<p title="{CJK}{EMOJI}">x</p>')
    assert f'title="{CJK}{EMOJI}"' in out


def test_wide_single_quoted_attribute_value() -> None:
    out = _body_text(f"<p title='{EMOJI}{CJK}'>x</p>")
    assert f'title="{EMOJI}{CJK}"' in out


def test_non_ascii_tag_name_is_unknown_atom() -> None:
    # a tag name that starts ASCII but carries wide characters is a non-1-byte
    # buffer, so it never interns to a known atom; it stays a plain element.
    # (a bare "<東" is not a tag at all - the name must open with an ASCII letter)
    name = f"a{CJK}"
    out = _body_text(f"<{name}>x</{name}>")
    assert f"<{name}>" in out


def test_non_ascii_attribute_name() -> None:
    # an attribute whose name is not 1-byte takes the per-character copy path;
    # the name is stored as bytes (a known limitation) but the element and its
    # value still parse, and the text after it lands in the body
    out = _body_text(f'<p {CJK}="1">x</p>')
    assert '="1"' in out
    assert '"x"' in out


def test_wide_input_with_carriage_return() -> None:
    # a CR in wide input forces the copy-and-normalize path; the CR becomes LF
    out = _body_text(f"<pre>{CJK}\r\n{EMOJI}</pre>")
    assert "\r" not in out
    assert CJK in out


def test_wide_input_with_nul() -> None:
    # a NUL in wide input sets the document NUL flag and is dropped from text
    out = _body_text(f"<p>{CJK}\x00{EMOJI}</p>")
    assert "\x00" not in out
    assert f"{CJK}{EMOJI}" in out


def test_rawtext_and_rcdata_wide_runs() -> None:
    # title is RCDATA, style is RAWTEXT; both take the wide run-scan
    assert CJK in _body_text(f"<title>{CJK}{EMOJI}</title>")
    assert EMOJI in _body_text(f"<style>{EMOJI}{CJK}</style>")


def test_plaintext_wide_run() -> None:
    # plaintext consumes the rest of the input through the wide run-scan
    assert f"{CJK}{EMOJI}" in _body_text(f"<plaintext>{CJK}{EMOJI}")
