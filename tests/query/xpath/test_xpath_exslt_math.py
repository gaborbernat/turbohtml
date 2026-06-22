"""EXSLT ``math:`` functions built into the XPath engine.

``math:min``, ``math:max``, ``math:highest``, ``math:lowest``, ``math:abs``, and
``math:power`` are reachable through the ``math:`` prefix without registering a
namespace, mirroring libexslt under lxml.
"""

from __future__ import annotations

import math

import pytest

import turbohtml
from turbohtml import Element

HTML = "<div id='nums'><n>3</n><n>1</n><n>5</n><n>5</n></div><div id='mixed'><m>3</m><m>nope</m></div>"


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


def texts(result: list[Element | str]) -> list[str]:
    return [node.text for node in result if isinstance(node, Element)]


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("math:max(//n)", 5.0, id="max"),
        pytest.param("math:min(//n)", 1.0, id="min"),
        pytest.param("math:abs(-4.5)", 4.5, id="abs-negative"),
        pytest.param("math:abs(4.5)", 4.5, id="abs-positive"),
        pytest.param("math:power(2, 10)", 1024.0, id="power"),
    ],
)
def test_math_numbers(doc: turbohtml.Node, expr: str, expected: float) -> None:
    assert doc.xpath(expr) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expr",
    [
        pytest.param("math:max(//m)", id="max-non-numeric"),
        pytest.param("math:min(//m)", id="min-non-numeric"),
        pytest.param("math:max(//absent)", id="max-empty"),
        pytest.param("math:min(//absent)", id="min-empty"),
    ],
)
def test_math_extreme_is_nan(doc: turbohtml.Node, expr: str) -> None:
    result = doc.xpath(expr)
    assert isinstance(result, float)
    assert math.isnan(result)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("math:highest(//n)", ["5", "5"], id="highest-ties"),
        pytest.param("math:lowest(//n)", ["1"], id="lowest"),
        pytest.param("math:highest(//m)", [], id="highest-non-numeric"),
        pytest.param("math:lowest(//absent)", [], id="lowest-empty"),
    ],
)
def test_math_select(doc: turbohtml.Node, expr: str, expected: list[str]) -> None:
    assert texts(doc.xpath(expr)) == expected


@pytest.mark.parametrize(
    "expr",
    [
        pytest.param("math:max('x')", id="max-non-nodeset"),
        pytest.param("math:highest('x')", id="highest-non-nodeset"),
    ],
)
def test_math_non_nodeset_argument_raises(doc: turbohtml.Node, expr: str) -> None:
    with pytest.raises(NotImplementedError, match="non-node-set"):
        doc.xpath(expr)
