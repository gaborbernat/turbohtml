from __future__ import annotations

from typing import Final

import pytest

from turbohtml import HTMLParseError, parse_xml


@pytest.mark.parametrize("count", [pytest.param(1, id="single"), pytest.param(1000, id="many")])
def test_xml_attribute_append_preserves_values_and_order(count: int) -> None:
    expected: Final = [(f"a{index}", str(index)) for index in range(count)]
    source: Final = "<root " + " ".join(f'{name}="{value}"' for name, value in expected) + "/>"
    root: Final = parse_xml(source).find("root")
    assert root is not None
    assert list(root.attrs.items()) == expected


@pytest.mark.parametrize(
    ("source", "code"),
    [
        pytest.param('<r a="1" a="2"/>', "xml-duplicate-attribute", id="lexical-duplicate"),
        pytest.param('<r p:a="1" p:a="2"/>', "xml-duplicate-attribute", id="duplicate-before-prefix-check"),
        pytest.param('<r xmlns:p="urn:a" xmlns:p=""/>', "xml-duplicate-attribute", id="duplicate-before-declaration"),
        pytest.param('<r a="1" a="&bad;"/>', "xml-undefined-entity", id="invalid-value-before-duplicate"),
    ],
)
def test_xml_attribute_append_preserves_first_error(source: str, code: str) -> None:
    with pytest.raises(HTMLParseError) as error:
        parse_xml(source)
    assert error.value.error.code == code


def test_xml_attribute_append_keeps_later_attribute_replacement() -> None:
    root: Final = parse_xml('<root a="before"/>').find("root")
    assert root is not None
    root.attrs["a"] = "after"
    root.attrs["b"] = "new"
    assert list(root.attrs.items()) == [("a", "after"), ("b", "new")]
