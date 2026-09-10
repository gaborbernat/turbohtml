from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element, parse, parse_xml


@pytest.mark.parametrize("count", [1, 29, 30, 100], ids=["small", "below-index", "index", "large"])
@pytest.mark.parametrize("position", ["first", "last"])
@pytest.mark.parametrize("different", [False, True], ids=["same", "different"])
def test_duplicate_normalized_attributes(count: int, position: str, *, different: bool) -> None:
    duplicates: Final = {"A": "x", "a": "y" if different else "x"}
    ordinary: Final = {f"data-{index}": "é水😀" for index in range(count)}
    attributes: Final = duplicates | ordinary if position == "first" else ordinary | duplicates
    left: Final = Element("div", attributes)
    right: Final = Element("div", attributes)
    assert left.equals(right) is not different


@pytest.mark.parametrize("prefix", ["data-", "é", "水", "𐐀"], ids=["ascii", "latin1", "ucs2", "ucs4"])
@pytest.mark.parametrize("different", [False, True], ids=["equal", "different"])
def test_xml_attribute_equality(prefix: str, *, different: bool) -> None:
    left: Final = parse_xml("<root " + " ".join(f'{prefix}{index}="{index}"' for index in range(40)) + "/>")
    right: Final = parse_xml(
        "<root "
        + " ".join(f'{prefix}{index}="{index + int(different and index == 39)}"' for index in reversed(range(40)))
        + "/>"
    )
    assert left.equals(right) is not different


@pytest.mark.parametrize("different", [False, True], ids=["equal", "different"])
def test_attribute_equality_with_sparse_atoms(*, different: bool) -> None:
    left: Final = Element("div")
    right: Final = Element("div")
    for index in range(40):
        left.attrs[f"data-{index}"] = str(index)
        right.attrs[f"data-{index}"] = str(index + int(different and index == 39))
        for filler in range(127):
            right.attrs[f"unused-{index}-{filler}"] = ""
            del right.attrs[f"unused-{index}-{filler}"]
    assert left.equals(right) is not different


@pytest.mark.parametrize("different", [False, True], ids=["equal", "different"])
def test_large_attribute_equality_within_one_tree(*, different: bool) -> None:
    document: Final = parse(
        "<div "
        + " ".join(f'data-{index}="{index}"' for index in range(40))
        + "></div><div "
        + " ".join(f'data-{index}="{index + int(different and index == 39)}"' for index in reversed(range(40)))
        + "></div>"
    )
    left, right = document.find_all("div")
    assert left.equals(right) is not different


def test_duplicate_attributes_reach_index_threshold_at_last_name() -> None:
    names: Final = [
        "".join(letter.upper() if variant & (1 << index) else letter for index, letter in enumerate("abcdef"))
        for variant in range(30)
    ]
    left: Final = Element("div", dict.fromkeys(names, "same") | {"penultimate": "x", "last": "y"})
    right: Final = Element(
        "div", {names[0]: "same", "penultimate": "x"} | dict.fromkeys(names[1:], "same") | {"last": "y"}
    )
    assert left.equals(right)


@pytest.mark.parametrize("different", [False, True], ids=["equal", "different"])
def test_many_duplicate_attributes_preserve_first_value(*, different: bool) -> None:
    names: Final = [
        "".join(letter.upper() if variant & (1 << index) else letter for index, letter in enumerate("abcdefghij"))
        for variant in range(1000)
    ]
    duplicates: Final = dict.fromkeys(names, "same")
    anchors: Final = {"first": "1", "second": "2", "third": "3"}
    left: Final = Element("div", anchors | duplicates)
    right: Final = Element("div", duplicates | anchors)
    if different:
        right.attrs[names[0]] = "different"
    assert left.equals(right) is not different
