from __future__ import annotations

import pytest

from turbohtml import parse


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param(
            '<meta property="og:title" content="Hello"><meta property="og:type" content="article">',
            {"og:title": "Hello", "og:type": "article"},
            id="opengraph-via-property",
        ),
        pytest.param(
            '<meta name="twitter:card" content="summary"><meta name="twitter:site" content="@x">',
            {"twitter:card": "summary", "twitter:site": "@x"},
            id="twitter-via-name",
        ),
        pytest.param('<meta name="og:title" content="By name">', {"og:title": "By name"}, id="og-via-name"),
        pytest.param(
            '<meta property="twitter:card" content="summary">',
            {"twitter:card": "summary"},
            id="twitter-via-property",
        ),
        pytest.param(
            '<meta property="og:title" name="twitter:title" content="P">',
            {"og:title": "P"},
            id="property-wins-over-name",
        ),
        pytest.param(
            '<meta property="description" name="og:title" content="N">',
            {"og:title": "N"},
            id="name-used-when-property-not-social",
        ),
        pytest.param(
            '<meta property name="og:title" content="N">',
            {"og:title": "N"},
            id="name-used-when-property-valueless",
        ),
        pytest.param('<meta property="og:title">', {"og:title": ""}, id="missing-content-empty-string"),
        pytest.param('<meta property="og:title" content>', {"og:title": ""}, id="valueless-content-empty-string"),
        pytest.param(
            '<meta property="og:title" content="first"><meta property="og:title" content="second">',
            {"og:title": "second"},
            id="last-occurrence-wins",
        ),
        pytest.param('<meta name="description" content="x">', {}, id="non-social-name"),
        pytest.param('<meta property="article:author" content="x">', {}, id="non-social-property"),
        pytest.param('<meta property="x" content="y">', {}, id="property-shorter-than-prefix"),
        pytest.param('<meta charset="utf-8">', {}, id="no-property-or-name"),
        pytest.param('<meta property name content="x">', {}, id="both-valueless"),
        pytest.param("<p>not a meta</p>", {}, id="no-meta"),
    ],
)
def test_opengraph(html: str, expected: dict[str, str]) -> None:
    assert parse(html).opengraph() == expected
