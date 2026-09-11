from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml import HTMLParseError, parse_xml


@pytest.mark.parametrize("prefix", ["p", "λ", "𐀀"], ids=["ascii", "ucs2", "ucs4"])
@pytest.mark.parametrize("count", [1, 128], ids=["single", "many"])
def test_xml_namespace_attribute_order(prefix: str, count: int) -> None:
    expected: Final = [(f"xmlns:{prefix}{index}", f"urn:{index}") for index in range(count)] + [
        (f"{prefix}{index}:value", "x") for index in range(count)
    ]
    root: Final = parse_xml("<root " + " ".join(f'{name}="{value}"' for name, value in expected) + "/>").find("root")
    assert root is not None
    assert list(root.attrs.items()) == expected


def test_xml_namespace_self_closing_rebinding() -> None:
    root: Final = parse_xml(
        '<root xmlns:p="urn:p" xmlns:q="urn:q"><before xmlns:p="urn:q" p:value="a"/>'
        '<after p:value="b" q:value="c"/></root>'
    ).find("after")
    assert root is not None
    assert list(root.attrs.items()) == [("p:value", "b"), ("q:value", "c")]


@pytest.mark.parametrize(
    ("source", "code"),
    [
        pytest.param(
            '<root xmlns:p="urn:p" xmlns:q="urn:q"><child xmlns:p="urn:q" p:value="a" q:value="b"/></root>',
            "xml-duplicate-attribute",
            id="rebound-collision",
        ),
        pytest.param(
            '<root xmlns:p="urn:p" xmlns:q="urn:p" p:value="a" q:value="b" missing:value="c"/>',
            "xml-undeclared-namespace",
            id="prefix-error-before-expanded-collision",
        ),
    ],
)
def test_xml_namespace_first_error(source: str, code: str) -> None:
    with pytest.raises(HTMLParseError) as error:
        parse_xml(source)
    assert error.value.error.code == code


@pytest.mark.parametrize(("index", "count"), [(0, 128), (1, 1)], ids=["many", "single"])
def test_lxml_namespace_benchmark_output(index: int, count: int) -> None:
    etree: Final = pytest.importorskip("lxml.etree", exc_type=ImportError)
    root: Final = etree.fromstring(cast("str", INPUTS["parse-xml-prefixes"]()[index][1]).encode())
    assert (root.tag, list(root.nsmap.items()), list(root.attrib.items()), len(root)) == (
        "root",
        [(f"p{number}", f"urn:{number}") for number in range(count)],
        [(f"{{urn:{number}}}value", "x") for number in range(count)],
        0,
    )
