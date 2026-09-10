from __future__ import annotations

import string
from typing import Final, cast

import pytest
from bench.ci import benchmarks
from bench.operations import INPUTS

from turbohtml import parse


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        pytest.param(0, "z" * 32768, id="map-32"),
        pytest.param(1, "z" * 32768, id="map-128"),
        pytest.param(2, "z" * 32768, id="map-512"),
        pytest.param(3, "a short title", id="short"),
        pytest.param(4, "A" * 32768, id="first-entry"),
        pytest.param(5, "b" * 32768, id="duplicates"),
        pytest.param(6, "b" * 64, id="long-map"),
        pytest.param(7, "B" * 32768, id="second-entry"),
        pytest.param(8, string.ascii_uppercase * 1260, id="ascii-cycle"),
        pytest.param(9, "".join(chr(384 + index) for index in range(128)) * 128, id="unicode-cycle"),
    ],
)
def test_translate_benchmark_result(case: int, expected: str) -> None:
    expression, source = cast("tuple[str, str]", INPUTS["xpath-translate"]()[case][1])
    document: Final = parse(source)
    assert document.xpath(expression) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("xpath-translate-repeated", "B" * 32768, id="repeated"),
        pytest.param("xpath-translate-long-map", "b" * 64, id="long-map"),
        pytest.param(
            "xpath-translate-varied",
            "".join(chr(384 + index) for index in range(128)) * 128,
            id="varied",
        ),
    ],
)
def test_codspeed_translate_result(name: str, expected: str) -> None:
    load: Final = next(load for identity, _, load in benchmarks() if identity == name)
    expression, source = cast("tuple[str, str]", load())
    assert parse(source).xpath(expression) == expected
