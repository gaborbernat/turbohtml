from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml import parse_fragment
from turbohtml.clean import Linker

_HTML: Final = pytest.importorskip("lxml.html")
_CLEAN: Final = pytest.importorskip("lxml_html_clean")


@pytest.mark.parametrize("case", [1, 2, 3, 4], ids=["wide", "ascii", "no-links", "many-links"])
def test_linkify_snapshot_outputs(case: int) -> None:
    source: Final = cast("str", INPUTS["linkify-node"]()[case][1])
    root: Final = _HTML.fragment_fromstring(source, create_parent="div")
    _CLEAN.autolink(root, avoid_hosts=())
    assert (
        Linker().linkify_node(parse_fragment(source)).inner_html,
        "".join(_HTML.tostring(child, encoding="unicode") for child in root),
    ) == (
        source.replace("https://example.com", '<a href="https://example.com" rel="nofollow">https://example.com</a>'),
        source.replace("https://example.com", '<a href="https://example.com">https://example.com</a>'),
    )
