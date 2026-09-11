from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml import Text, parse_fragment
from turbohtml.clean import LinkCandidate, Linker, Linkify, nofollow, target_blank


@pytest.mark.parametrize("prefix", ["plain ", "café ", "中文 ", "😀 "], ids=["ascii", "latin1", "ucs2", "ucs4"])
def test_linkify_snapshot_width(prefix: str) -> None:
    assert Linker().linkify(prefix + "https://example.com tail") == (
        prefix + '<a href="https://example.com" rel="nofollow">https://example.com</a> tail'
    )


@pytest.mark.parametrize("prefix", ["plain ", "😀 "], ids=["ascii", "ucs4"])
def test_linkify_snapshot_survives_callback_mutation(prefix: str) -> None:
    root: Final = parse_fragment(prefix + "https://example.com tail")
    text: Final = root.children[0]
    assert isinstance(text, Text)

    def mutate(link: LinkCandidate) -> LinkCandidate:
        text.data = "replaced by callback"
        return link

    assert Linker(Linkify(callbacks=(mutate,))).linkify_node(root).inner_html == (
        prefix + '<a href="https://example.com">https://example.com</a> tail'
    )


def test_linkify_wide_snapshot_callback_veto() -> None:
    def veto(_link: LinkCandidate) -> None:
        return None

    assert Linker(Linkify(callbacks=(veto,))).linkify("😀 https://example.com tail") == "😀 https://example.com tail"


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        pytest.param(
            1,
            "<p>" + "😀 " * 32_768 + '<a href="https://example.com" rel="nofollow">https://example.com</a></p>',
            id="wide-one-link",
        ),
        pytest.param(
            2,
            "<p>" + "a " * 32_768 + '<a href="https://example.com" rel="nofollow">https://example.com</a></p>',
            id="ascii-one-link",
        ),
        pytest.param(3, "<p>" + "😀 " * 32_768 + "</p>", id="wide-no-links"),
        pytest.param(
            4,
            "<p>" + '😀 <a href="https://example.com" rel="nofollow">https://example.com</a> ' * 1_024 + "</p>",
            id="wide-many-links",
        ),
    ],
)
def test_linkify_snapshot_benchmark(case: int, expected: str) -> None:
    root: Final = parse_fragment(cast("str", INPUTS["linkify-node"]()[case][1]))
    assert Linker().linkify_node(root).inner_html == expected


def test_linkify_snapshot_callback_benchmark() -> None:
    case: Final = cast("tuple[str, str]", INPUTS["linkify-traversal"]()[5][1])
    assert Linker(Linkify(callbacks=(nofollow, target_blank), process_existing=True)).linkify(case[1]) == (
        "<p>"
        + "😀 " * 32_768
        + '<a href="https://example.com" rel="nofollow" target="_blank">https://example.com</a></p>'
    )
