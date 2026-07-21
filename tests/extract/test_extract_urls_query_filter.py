"""The query_allow/query_deny parameter filters and the w3lib canonicalize preset on UrlCleaning."""

from __future__ import annotations

import pytest

from turbohtml.extract import UrlCleaning, clean_url, normalize_url


@pytest.mark.parametrize(
    ("url", "options", "expected"),
    [
        pytest.param(
            "http://x.org/p?id=200&foo=bar&name=wired",
            UrlCleaning(query_allow=frozenset({"id", "name"})),
            "http://x.org/p?id=200&name=wired",
            id="allow-keeps-only-listed",
        ),
        pytest.param(
            "http://x.org/p?utm_source=kept&id=1",
            UrlCleaning(query_allow=frozenset({"utm_source"})),
            "http://x.org/p?utm_source=kept",
            id="allowed-tracker-survives",
        ),
        pytest.param(
            "http://x.org/p?ID=2&Name=x",
            UrlCleaning(query_allow=frozenset({"id"})),
            "http://x.org/p?ID=2",
            id="allow-matches-case-insensitively",
        ),
        pytest.param(
            "http://x.org/p?id=200&foo=bar&name=wired",
            UrlCleaning(query_deny=frozenset({"id", "foo"})),
            "http://x.org/p?name=wired",
            id="deny-drops-listed",
        ),
        pytest.param(
            "http://x.org/p?utm_source=x&keep=1&drop=2",
            UrlCleaning(query_deny=frozenset({"drop"})),
            "http://x.org/p?keep=1",
            id="deny-composes-with-tracker-removal",
        ),
        pytest.param(
            "http://x.org/p?page=2&post=abc&id=1",
            UrlCleaning(strict=True, query_deny=frozenset({"post"})),
            "http://x.org/p?id=1&page=2",
            id="deny-composes-with-strict",
        ),
        pytest.param(
            "http://x.org/p?b=2&a=1#mtm_campaign=doc&keep=1",
            UrlCleaning(query_deny=frozenset({"keep"})),
            "http://x.org/p?a=1&b=2",
            id="fragment-scrub-honors-deny",
        ),
    ],
)
def test_query_filters(url: str, options: UrlCleaning, expected: str) -> None:
    assert normalize_url(url, options) == expected


def test_strict_and_allow_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        UrlCleaning(strict=True, query_allow=frozenset({"id"}))


def test_w3lib_preset_drops_the_fragment() -> None:
    assert UrlCleaning.w3lib() == UrlCleaning(strip_fragment=True)


def test_w3lib_preset_canonicalizes_like_canonicalize_url() -> None:
    url = "http://www.example.com/do?c=3&b=5&b=2&a=50#frag"
    assert normalize_url(url, UrlCleaning.w3lib()) == "http://www.example.com/do?a=50&b=2&b=5&c=3"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param("https://x.org/p?wickedclid=1&keep=2", "https://x.org/p?keep=2", id="clid-suffix-dropped"),
        pytest.param("https://x.org/p?lucid=1", "https://x.org/p?lucid=1", id="near-miss-lucid-kept"),
        pytest.param("https://x.org/p?ref_source=1", "https://x.org/p", id="tracker-word-underscore"),
        pytest.param("https://x.org/p?reference=1", "https://x.org/p?reference=1", id="longer-word-kept"),
    ],
)
def test_tracker_suffix_and_word_boundaries(url: str, expected: str) -> None:
    assert clean_url(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param("https://x.org/a/%2E%2E/b", "https://x.org/b", id="uppercase-escape-parent"),
        pytest.param("https://x.org/a/%2E/b", "https://x.org/a/b", id="uppercase-escape-self"),
        pytest.param("https://x.org/a/../../b", "https://x.org/b", id="parent-past-root-clamps"),
        # a trailing dot segment resolves to the directory, so the slash survives (path state, spec 4.4)
        pytest.param("https://x.org/a/b/..", "https://x.org/a/", id="trailing-parent-keeps-slash"),
        pytest.param("https://x.org/a/.", "https://x.org/a/", id="trailing-self-keeps-slash"),
        pytest.param("https://x.org/...", "https://x.org/...", id="triple-dot-is-a-segment"),
    ],
)
def test_dot_segment_resolution(url: str, expected: str) -> None:
    assert clean_url(url) == expected
