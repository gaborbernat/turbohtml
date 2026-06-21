"""Behavioral tests for the public IncrementalParser (push parse to a tree).

The treebuilder conformance suite (test_treebuilder_conformance.py) pins the
whole-document algorithm to the WHATWG spec; these tests cover what it cannot:
that feeding a document in arbitrary chunks resumes the tree builder in place and
yields exactly the Document that parse() builds from the whole string, plus the
bytes-decoding, lifecycle, and error surface of the push API.
"""

from __future__ import annotations

import pytest

from turbohtml import Document, IncrementalParser, parse

# Each fixture exercises a different resumable corner of the tree builder: text and
# attributes, rawtext (script/style/title/textarea) whose content can split across a
# feed, table foster-parenting, select, template, foreign content, the adoption
# agency, comments, doctype, and CR normalization.
DOCUMENTS = [
    pytest.param("", id="empty"),
    pytest.param("<!DOCTYPE html><p class=x>Hello <b>wo</b>rld</p>", id="doctype-text-attr"),
    pytest.param("<title>A &amp; B</title><script>var x = 1 < 2;</script>", id="rawtext"),
    pytest.param("<textarea>\nkept</textarea><style>p{color:red}</style>", id="textarea-style"),
    pytest.param("<table><tr><td>cell</td></tr>stray<caption>c</caption></table>", id="table-foster"),
    pytest.param("<select><option>a<option>b</select><p>after", id="select"),
    pytest.param("<template><tr><td>x</td></tr></template>", id="template"),
    pytest.param("<svg><circle/><foreignObject><div>d</div></foreignObject></svg>", id="foreign"),
    pytest.param("<b>1<i>2</b>3</i>4", id="adoption-agency"),
    pytest.param("<!-- a comment --><p>after the comment</p>", id="comment"),
    pytest.param("<div><p>a<p>b<p>c</div>", id="implied-end-tags"),
    pytest.param("line one\r\nline two\rline three", id="cr-normalization"),
    pytest.param("<p>n\x00ul</p>", id="nul"),
    pytest.param("plain text with no tags at all", id="plain-text"),
]

CHUNK_SIZES = [pytest.param(size, id=f"chunk-{size}") for size in (1, 2, 3, 5, 8, 13)]


def _stream(document: str, chunk: int) -> str:
    parser = IncrementalParser()
    for start in range(0, len(document), chunk):
        parser.feed(document[start : start + chunk])
    return parser.close().html


@pytest.mark.parametrize("document", DOCUMENTS)
@pytest.mark.parametrize("chunk", CHUNK_SIZES)
def test_chunked_str_matches_whole(document: str, chunk: int) -> None:
    assert _stream(document, chunk) == parse(document).html


@pytest.mark.parametrize("document", DOCUMENTS)
def test_one_character_at_a_time_matches_whole(document: str) -> None:
    parser = IncrementalParser()
    for character in document:
        parser.feed(character)
    assert parser.close().html == parse(document).html


# A U+0000 makes the text builder filter NUL; the streaming path must flag it from
# whatever storage width the fed chunk happens to use, so feed each width whole.
WIDE_WIDTHS = [
    pytest.param("<p>café ☃ two-byte plain</p>", id="two-byte"),
    pytest.param("<p>café\x00☃ two-byte nul</p>", id="two-byte-nul"),
    pytest.param("<p>math 🦄 four-byte plain</p>", id="four-byte"),
    pytest.param("<p>🦄\x00 four-byte nul</p>", id="four-byte-nul"),
]


@pytest.mark.parametrize("document", WIDE_WIDTHS)
def test_wide_storage_widths_single_feed_match_whole(document: str) -> None:
    parser = IncrementalParser()
    parser.feed(document)  # one feed keeps the chunk at the string's natural width
    assert parser.close().html == parse(document).html


def test_close_returns_a_document() -> None:
    parser = IncrementalParser()
    parser.feed("<p>hi</p>")
    document = parser.close()
    assert isinstance(document, Document)
    paragraph = document.find("p")
    assert paragraph is not None
    assert paragraph.text == "hi"


def test_str_parse_has_no_encoding() -> None:
    parser = IncrementalParser()
    parser.feed("<p>x</p>")
    assert parser.close().encoding is None


def test_empty_close_builds_the_skeleton() -> None:
    assert IncrementalParser().close().html == parse("").html
