"""Conformance tests for the C ``_url_variant_key`` behind :func:`turbohtml.extract.extract_links`.

The key collapses the scheme and a bare trailing slash so the ``http``/``https`` and slash twins of one address
deduplicate: it is everything after the first ``"://"``, with the trailing slash run trimmed unless the remainder holds
a ``?`` or ``#`` (where a slash is content). Coverage is a differential against that partition/rstrip expression.
"""

from __future__ import annotations

import itertools

import pytest

from turbohtml._html import _url_variant_key


def _oracle_variant(url: str) -> str:
    remainder = url.partition("://")[2]
    return remainder if "?" in remainder or "#" in remainder else remainder.rstrip("/")


_SCHEMES = ("https://", "http://", "ftp://", "", "://", "a://b://")
_TAILS = (
    "",
    "/",
    "//",
    "x.example/p",
    "x.example/p/",
    "x.example/p//",
    "x.example/p?q=1",
    "x.example/p/#f",
    "x.example/a/b/",
    "x.example/?only",
    "x.example/#only",
    "mailto:x@y",
    "a:/b/c/",
)


def _corpus() -> list[str]:
    combined = {"".join(combo) for combo in itertools.product(_SCHEMES, _TAILS)}
    return sorted(combined | {"", "no-scheme-path/", "://leading/", "a://b://c/d/"})


def test_variant_key_matches_oracle_over_corpus() -> None:
    for url in _corpus():
        assert _url_variant_key(url) == _oracle_variant(url), repr(url)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param("", "", id="empty"),
        pytest.param("no-scheme-path/", "", id="no-scheme-empty-key"),
        pytest.param("https://x/p/", "x/p", id="trailing-slash-trimmed"),
        pytest.param("https://x/p///", "x/p", id="trailing-slashes-trimmed"),
        pytest.param("https://x/p?q=1/", "x/p?q=1/", id="query-keeps-slash"),
        pytest.param("https://x/p/#f", "x/p/#f", id="fragment-keeps-slash"),
        pytest.param("https://x/", "x", id="root-slash-trimmed"),
        pytest.param("a://b://c/", "b://c", id="first-marker-wins"),
        pytest.param("mailto:x@y", "", id="colon-not-followed-by-slash"),
        pytest.param("a:/b/c/", "", id="colon-single-slash-no-marker"),
    ],
)
def test_variant_key_cases(url: str, expected: str) -> None:
    assert _url_variant_key(url) == expected


def test_variant_key_rejects_non_str() -> None:
    with pytest.raises(TypeError, match="must be str"):
        _url_variant_key(123)  # ty: ignore[invalid-argument-type]  # a non-str exercises the TypeError guard
