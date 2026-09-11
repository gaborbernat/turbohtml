from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml import HTMLParseError, parse_xml


@pytest.mark.parametrize("quote", ['"', "'"], ids=["double", "single"])
@pytest.mark.parametrize("character", ["a", "é", "λ", "𐀀"], ids=["ascii", "latin1", "ucs2", "ucs4"])
@pytest.mark.parametrize("length", [0, 65, 65536], ids=["empty", "growth", "long"])
def test_xml_attribute_run_value(quote: str, character: str, length: int) -> None:
    value: Final = character * length
    root: Final = parse_xml(f"<root value={quote}{value}{quote}/>").find("root")
    assert root is not None
    assert root.attrs["value"] == value


@pytest.mark.parametrize("quote", ['"', "'"], ids=["double", "single"])
def test_xml_attribute_run_normalization(quote: str) -> None:
    root: Final = parse_xml(f"<root value={quote}" + "a" * 80 + f"&amp;b\t&#9;\r\n{quote}/>").find("root")
    assert root is not None
    assert root.attrs["value"] == "a" * 80 + "&b \t "


def test_xml_attribute_run_scratch_reuse() -> None:
    long: Final = "a" * 1024
    root: Final = parse_xml(f'<root first="{long}" second="short" third="{long}"/>').find("root")
    assert root is not None
    assert list(root.attrs.items()) == [("first", long), ("second", "short"), ("third", long)]


@pytest.mark.parametrize(
    ("tail", "code"),
    [
        pytest.param("<", "xml-lt-in-attribute", id="markup"),
        pytest.param("\x00", "xml-invalid-char", id="null"),
        pytest.param("\x01", "xml-invalid-char", id="control"),
    ],
)
def test_xml_attribute_run_error_position(tail: str, code: str) -> None:
    with pytest.raises(HTMLParseError) as error:
        parse_xml('<root a="' + "a" * 80 + tail + '"/>')
    assert (error.value.error.code, error.value.error.line, error.value.error.col) == (code, 1, 89)


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, "a" * 65536), (1, "a&b " * 8192), (2, "hello")],
    ids=["clean", "references", "tiny"],
)
def test_xml_value_benchmark_output(index: int, expected: str) -> None:
    root: Final = parse_xml(cast("str", INPUTS["parse-xml-values"]()[index][1])).find("root")
    assert root is not None
    assert root.attrs["value"] == expected
