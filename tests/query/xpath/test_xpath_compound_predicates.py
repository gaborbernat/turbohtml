"""Regression: a predicated location path keeps its predicate inside a compound
expression.

The XPath parser stored a step's predicate list with
``nodes[step].first = parse_predicates(ps)``. ``parse_predicates`` calls ``xn_new``,
which can reallocate the arena, so the left-hand address (taken from the pre-call
``nodes`` pointer) could dangle and the store be lost -- silently dropping the
predicate of a path parsed across an arena growth. Whether the growth landed on a
given predicate depended on the surrounding node count, so wrapping a union in a
function call (``count(//a[@x] | //b[@y])``) could drop the second path's predicate.
"""

from __future__ import annotations

import pytest

import turbohtml

HTML = "<r><a x='1'>A</a><b y='2'>B</b><b>B2</b></r>"


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        pytest.param("count(//a[@x='1'] | //b[@y='2'])", 2.0, id="union-in-count"),
        pytest.param("count(//b[@y='2'] | //a[@x='1'])", 2.0, id="union-in-count-swapped"),
        pytest.param("//a[@x='1'] | //b[@y='2']", None, id="union-root"),
    ],
)
def test_predicate_survives_in_compound_expression(doc: turbohtml.Node, expr: str, expected: float | None) -> None:
    result = doc.xpath(expr)
    if expected is None:
        assert len(result) == 2
    else:
        assert result == pytest.approx(expected)
