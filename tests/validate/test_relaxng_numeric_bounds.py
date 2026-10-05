from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG

_NAMESPACE: Final = "http://relaxng.org/ns/structure/1.0"
_LIBRARY: Final = "http://www.w3.org/2001/XMLSchema-datatypes"


@pytest.mark.parametrize("datatype", ["integer", "decimal", "double"])
@pytest.mark.parametrize("attribute", [pytest.param(False, id="text"), pytest.param(True, id="attribute")])
@pytest.mark.parametrize(
    ("facet", "value", "expected"),
    [
        pytest.param("minInclusive", "0", False, id="min-inclusive-below"),
        pytest.param("minInclusive", "1", True, id="min-inclusive-equal"),
        pytest.param("minInclusive", "2", True, id="min-inclusive-above"),
        pytest.param("maxInclusive", "0", True, id="max-inclusive-below"),
        pytest.param("maxInclusive", "1", True, id="max-inclusive-equal"),
        pytest.param("maxInclusive", "2", False, id="max-inclusive-above"),
        pytest.param("minExclusive", "0", False, id="min-exclusive-below"),
        pytest.param("minExclusive", "1", False, id="min-exclusive-equal"),
        pytest.param("minExclusive", "2", True, id="min-exclusive-above"),
        pytest.param("maxExclusive", "0", True, id="max-exclusive-below"),
        pytest.param("maxExclusive", "1", False, id="max-exclusive-equal"),
        pytest.param("maxExclusive", "2", False, id="max-exclusive-above"),
        pytest.param("minInclusive", "invalid", False, id="invalid-lexical"),
    ],
)
def test_rng_numeric_bound(datatype: str, facet: str, value: str, *, attribute: bool, expected: bool) -> None:
    pattern: Final = f'<data type="{datatype}"><param name="{facet}">1</param></data>'
    validator: Final = RelaxNG(
        f'<element xmlns="{_NAMESPACE}" datatypeLibrary="{_LIBRARY}" name="doc">'
        + (f'<attribute name="value">{pattern}</attribute>' if attribute else pattern)
        + "</element>"
    )
    document: Final = f'<doc value="{value}"/>' if attribute else f"<doc>{value}</doc>"
    assert tuple(validator.validate(parse_xml(document)).valid for _ in range(2)) == (expected, expected)


@pytest.mark.parametrize("facet", ["minInclusive", "maxInclusive", "minExclusive", "maxExclusive"])
def test_rng_numeric_bound_nan(facet: str) -> None:
    validator: Final = RelaxNG(
        f'<element xmlns="{_NAMESPACE}" datatypeLibrary="{_LIBRARY}" name="doc">'
        f'<data type="double"><param name="{facet}">1</param></data></element>'
    )
    assert tuple(validator.validate(parse_xml("<doc>NaN</doc>")).valid for _ in range(2)) == (False, False)


@pytest.mark.parametrize(
    ("datatype", "params", "value", "expected"),
    [
        pytest.param("double", "", "NaN", True, id="unbounded-nan"),
        pytest.param("double", "", "INF", True, id="unbounded-positive-infinity"),
        pytest.param("double", "", "-INF", True, id="unbounded-negative-infinity"),
        pytest.param("double", "", "2", True, id="unbounded-finite"),
        pytest.param("double", "", "invalid", False, id="unbounded-invalid"),
        pytest.param(
            "double",
            '<param name="minInclusive">0</param><param name="maxInclusive">1</param>',
            "0.5",
            True,
            id="two-bounds-inside",
        ),
        pytest.param(
            "double",
            '<param name="minInclusive">0</param><param name="maxInclusive">1</param>',
            "INF",
            False,
            id="two-bounds-positive-infinity",
        ),
        pytest.param(
            "double",
            '<param name="minInclusive">0</param><param name="maxInclusive">1</param>',
            "-INF",
            False,
            id="two-bounds-negative-infinity",
        ),
        pytest.param("double", '<param name="maxInclusive">1</param>', "1e0", True, id="exponent-equal"),
        pytest.param("double", '<param name="maxInclusive">1</param>', " 0.5 ", True, id="normalized-space"),
        pytest.param(
            "date",
            '<param name="maxExclusive">2024-12-31</param>',
            "2024-01-01",
            True,
            id="date-keeps-calendar-comparison",
        ),
    ],
)
def test_rng_numeric_bound_controls(datatype: str, params: str, value: str, *, expected: bool) -> None:
    validator: Final = RelaxNG(
        f'<element xmlns="{_NAMESPACE}" datatypeLibrary="{_LIBRARY}" name="doc">'
        f'<data type="{datatype}">{params}</data></element>'
    )
    assert tuple(validator.validate(parse_xml(f"<doc>{value}</doc>")).valid for _ in range(2)) == (expected, expected)
