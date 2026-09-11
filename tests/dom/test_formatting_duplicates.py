from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse


@pytest.mark.parametrize("distinct", [pytest.param(True, id="distinct-values"), pytest.param(False, id="same-values")])
def test_formatting_duplicate_scan_keeps_all_source_elements(*, distinct: bool) -> None:
    values: Final = [str(index) if distinct else "same" for index in range(256)]
    source: Final = "".join(f'<b title="{value}">' for value in values) + "a" + "</b>" * 256
    assert [(element.attrs["title"], element.text) for element in parse(source).find_all("b")] == [
        (value, "a") for value in values
    ]


@pytest.mark.parametrize(
    ("other", "attributes"),
    [
        pytest.param('title="other"', {"title": "other"}, id="different-value"),
        pytest.param('id="same"', {"id": "same"}, id="different-name"),
        pytest.param('title="else"', {"title": "else"}, id="same-length-value"),
        pytest.param("", {}, id="different-attribute-count"),
    ],
)
def test_formatting_duplicate_limit_keeps_distinct_attributes(other: str, attributes: dict[str, str]) -> None:
    source: Final = '<p><b title="same">' + f"<b {other}>" + '<b title="same">' * 3 + "one</p>two"
    assert [(element.text, dict(element.attrs)) for element in parse(source).find_all("b")] == [
        ("one", {"title": "same"}),
        ("one", attributes),
        *[("one", {"title": "same"})] * 3,
        ("two", attributes),
        *[("two", {"title": "same"})] * 3,
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "<b><object><i>one</i></object><b>two",
            "<b><object><i>one</i></object><b>two</b></b>",
            id="outer-formatting-across-object-marker",
        ),
        pytest.param(
            "<p><b><i><b><b><b>one</p>two",
            "<p><b><i><b><b><b>one</b></b></b></i></b></p><i><b><b><b>two</b></b></b></i>",
            id="different-formatting-name",
        ),
    ],
)
def test_formatting_duplicate_limit_preserves_nested_structure(source: str, expected: str) -> None:
    root: Final = parse(source).find("body")
    assert root is not None
    assert root.inner_html == expected


def test_formatting_duplicate_checks_first_of_multiple_attributes() -> None:
    source: Final = (
        '<p><b title="same" lang="en"><b title="other" lang="en">' + '<b title="same" lang="en">' * 3 + "one</p>two"
    )
    assert [(element.text, dict(element.attrs)) for element in parse(source).find_all("b")] == [
        ("one", {"title": "same", "lang": "en"}),
        ("one", {"title": "other", "lang": "en"}),
        *[("one", {"title": "same", "lang": "en"})] * 3,
        ("two", {"title": "other", "lang": "en"}),
        *[("two", {"title": "same", "lang": "en"})] * 3,
    ]
