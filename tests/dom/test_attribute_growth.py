from __future__ import annotations

from copy import deepcopy
from typing import Final

import pytest

from turbohtml import Element, parse, parse_xml
from turbohtml.mutations import MutationObserver


@pytest.mark.parametrize("count", [pytest.param(3, id="small"), pytest.param(100, id="wide")])
def test_attribute_growth_preserves_values_and_order(count: int) -> None:
    root: Final = Element("p")
    for index in range(count):
        root.attrs[f"data-{index}"] = str(index)
    root.attrs["data-0"] = "changed"
    del root.attrs["data-1"]
    root.attrs["data-last"] = "last"
    assert list(root.attrs.items()) == [
        ("data-0", "changed"),
        *((f"data-{index}", str(index)) for index in range(2, count)),
        ("data-last", "last"),
    ]


def test_attribute_growth_keeps_copies_independent() -> None:
    root: Final = Element("p")
    for name in ("a", "b", "c"):
        root.attrs[f"data-{name}"] = name
    copied: Final = deepcopy(root)
    root.attrs["data-d"] = "original"
    copied.attrs["data-d"] = "copy"
    assert (root.attrs["data-d"], copied.attrs["data-d"]) == ("original", "copy")


def test_attribute_growth_preserves_parsed_attributes() -> None:
    root: Final = parse('<p title="original" hidden></p>').find("p")
    assert root is not None
    for index in range(100):
        root.attrs[f"data-{index}"] = str(index)
    assert list(root.attrs.items()) == [
        ("title", "original"),
        ("hidden", ""),
        *((f"data-{index}", str(index)) for index in range(100)),
    ]


def test_attribute_growth_records_changes_across_capacity_boundaries() -> None:
    root: Final = Element("p")
    observer: Final = MutationObserver()
    observer.observe(root, attributes=True, attribute_old_value=True)
    for index in range(17):
        root.attrs[f"data-{index}"] = str(index)
    root.attrs["data-0"] = "changed"
    del root.attrs["data-1"]
    root.attrs["data-1"] = "restored"
    assert [(record.attribute_name, record.old_value) for record in observer.take_records()] == [
        *((f"data-{index}", None) for index in range(17)),
        ("data-0", "0"),
        ("data-1", "1"),
        ("data-1", None),
    ]


@pytest.mark.parametrize("count", [3, 100], ids=["small", "wide"])
def test_attribute_growth_preserves_xml_names_and_values(count: int) -> None:
    attributes: Final = " ".join(f'名{index}="é😀{index}"' for index in range(count))
    root: Final = parse_xml(f"<root {attributes}/>").find("root")
    assert root is not None
    root.attrs["追加"] = "追加値"
    assert list(root.attrs.items()) == [
        *((f"名{index}", f"é😀{index}") for index in range(count)),
        ("追加", "追加値"),
    ]
