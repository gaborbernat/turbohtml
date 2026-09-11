from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml import HTMLParseError, parse_xml


@pytest.mark.parametrize("length", [0, 7, 8, 16], ids=["start", "last-byte", "next-block", "two-blocks"])
@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        pytest.param("end", "end", id="plain"),
        pytest.param("&amp;end", "&end", id="reference"),
        pytest.param("\r\nend", "\nend", id="crlf"),
        pytest.param("]end", "]end", id="bracket"),
        pytest.param("<child/>end", "end", id="markup"),
    ],
)
def test_xml_text_block_boundary(length: int, tail: str, expected: str) -> None:
    root: Final = parse_xml("<root>" + "a" * length + tail + "</root>").find("root")
    assert root is not None
    assert root.text == "a" * length + expected


@pytest.mark.parametrize("text", ["a", "é", "λ", "𐀀"], ids=["ascii", "latin1", "ucs2", "ucs4"])
def test_xml_text_block_width(text: str) -> None:
    root: Final = parse_xml("<root>" + text * 65536 + "</root>").find("root")
    assert root is not None
    assert root.text == text * 65536


@pytest.mark.parametrize("length", [7, 8, 16], ids=["last-byte", "next-block", "two-blocks"])
@pytest.mark.parametrize(
    ("tail", "code"),
    [
        pytest.param("\x00", "xml-invalid-char", id="null"),
        pytest.param("\x01", "xml-invalid-char", id="control"),
        pytest.param("]]>", "xml-cdata-close-in-content", id="cdata-close"),
    ],
)
def test_xml_text_block_error_position(length: int, tail: str, code: str) -> None:
    with pytest.raises(HTMLParseError) as error:
        parse_xml("<root>" + "a" * length + tail + "</root>")
    assert (error.value.error.code, error.value.error.line, error.value.error.col) == (code, 1, length + 6)


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, "a" * 65536), (1, "a&b " * 8192), (2, "hello")],
    ids=["clean", "references", "tiny"],
)
def test_xml_text_benchmark_output(index: int, expected: str) -> None:
    root: Final = parse_xml(cast("str", INPUTS["parse-xml-text"]()[index][1])).find("root")
    assert root is not None
    assert root.text == expected
