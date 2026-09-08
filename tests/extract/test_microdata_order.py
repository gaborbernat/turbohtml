"""Repeated property names expose ordering changes that distinct keys can hide."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import MicrodataItem, parse

if TYPE_CHECKING:
    from turbohtml import Document


@pytest.mark.parametrize(
    "reference",
    [
        pytest.param("", id="absent"),
        pytest.param("itemref", id="valueless"),
        pytest.param('itemref=""', id="empty"),
        pytest.param('itemref=" "', id="whitespace"),
        pytest.param("itemref=missing", id="unresolved"),
        pytest.param('itemref="last first last"', id="overlapping"),
    ],
)
def test_microdata_repeated_values_follow_tree_order(reference: str) -> None:
    document: Final[Document] = parse(
        f"<div itemscope {reference}>stray<!--comment-->"
        "<section><span id=first itemprop=name>first</span></section>"
        "<div itemprop=name>outer<span itemprop=name>inner</span></div>"
        "<span id=last itemprop=name>last</span></div>"
    )
    assert document.microdata() == [
        MicrodataItem(type=None, id=None, properties={"name": ["first", "outerinner", "inner", "last"]})
    ]


def test_microdata_nested_scope_keeps_following_properties() -> None:
    document: Final[Document] = parse(
        "<div itemscope><section itemprop=child itemscope>"
        "<span itemprop=name>child</span></section><span itemprop=name>parent</span></div>"
    )
    assert document.microdata() == [
        MicrodataItem(
            type=None,
            id=None,
            properties={
                "child": [MicrodataItem(type=None, id=None, properties={"name": ["child"]})],
                "name": ["parent"],
            },
        )
    ]


def test_microdata_wide_item_keeps_all_values() -> None:
    document: Final[Document] = parse(
        "<div itemscope>" + "".join(f"<span itemprop=name>{index}</span>" for index in range(1_000)) + "</div>"
    )
    assert document.microdata() == [
        MicrodataItem(type=None, id=None, properties={"name": [str(index) for index in range(1_000)]})
    ]


@pytest.mark.parametrize("reference", [pytest.param("", id="local"), pytest.param("itemref=hidden", id="referenced")])
@pytest.mark.parametrize(
    "attribute", [pytest.param("itemprop", id="valueless"), pytest.param('itemprop=""', id="empty")]
)
def test_microdata_empty_property_skips_cyclic_item_graph(reference: str, attribute: str) -> None:
    document: Final[Document] = parse(
        f"<div itemscope {reference}><span itemprop=name>kept</span>"
        f"<div id=hidden itemscope {attribute} itemref=first></div></div>"
        "<div id=first itemscope itemprop=child itemref=second></div>"
        "<div id=second itemscope itemprop=child itemref=first></div>"
    )
    assert document.microdata() == [MicrodataItem(type=None, id=None, properties={"name": ["kept"]})]
