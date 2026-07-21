"""Conformance tests for the C ``_url_language_matches`` behind :func:`turbohtml.extract.clean_url`'s language filter.

The filter judges a URL's own language markers against a target language: a ``lang``/``language`` query parameter whose
value does not start with the target, a leading path segment that is an ISO 639-1 tag of another language, and -- in
strict mode -- a two-letter host label of another language. Coverage is a differential against the Python heuristics the
port replaced, over a corpus that reaches each segment shape and marker.
"""

from __future__ import annotations

import itertools
import re

import pytest

from turbohtml._html import _url_language_matches, _url_percent_decode

_LANGUAGE_PARAMS = frozenset({"lang", "language"})
_ISO = frozenset({"de", "en", "fr", "es", "ru", "nl"})
_SEGMENT = re.compile(r"([a-z]{2})(?:[-_][a-z]{2,3})?$")


def _oracle(query: str, path: str, hostname: str, language: str, *, strict: bool) -> bool:
    for pair in query.split("&"):
        key, separator, value = pair.partition("=")
        if separator and _url_percent_decode(key).lower() in _LANGUAGE_PARAMS:
            code = _url_percent_decode(value).lower()
            if code and not code.startswith(language):
                return False
    leading = next((segment for segment in path.lower().split("/") if segment), "")
    if (match := _SEGMENT.fullmatch(leading)) and match[1] in _ISO and match[1] != language:
        return False
    if strict:
        label = hostname.partition(".")[0]
        if len(label) == 2 and label in _ISO and label != language:
            return False
    return True


_PATHS = (
    "",
    "/",
    "/de/beitrag",
    "/en-us/page",
    "/en_us/page",
    "/fr-fra/x",
    "/de",
    "//de//x",
    "de/x",
    "/DE/UPPER",
    "/e1/x",
    "/abc/x",
    "/abcd/x",
    "/en-u1/x",
    "/en-u/x",
    "/xy-ab/x",
    "/ru/y",
    "/zz/y",
    "/en-abcd/x",
    "/%64%65/x",
    "/enxab/x",
    "/z{/x",
)
_QUERIES = (
    "",
    "x=1",
    "lang=de",
    "language=fr",
    "lang=en-US",
    "lang=",
    "lang=de&language=en",
    "LANG=fr",
    "%6c%61%6e%67=de",
)
_HOSTS = ("example.org", "de.example.org", "en.example.org", "zz.example.org", "e.org", "fr.a.b", "de", "localhost")
_LANGS = ("de", "en", "fr")


def test_language_matches_matches_oracle_over_corpus() -> None:
    for path, query, host, lang, strict in itertools.product(_PATHS, _QUERIES, _HOSTS, _LANGS, (False, True)):
        got = _url_language_matches(query, path, host, lang, strict, _LANGUAGE_PARAMS, _ISO)
        want = _oracle(query, path, host, lang, strict=strict)
        assert got is want, (query, path, host, lang, strict)


@pytest.mark.parametrize(
    ("markers", "strict", "expected"),
    [
        pytest.param(("", "/de/x", "h.org", "en"), False, False, id="path-segment-other-language"),
        pytest.param(("", "/en/x", "h.org", "en"), False, True, id="path-segment-same-language"),
        pytest.param(("", "/en-us/x", "h.org", "en"), False, True, id="path-subtag-two-letters"),
        pytest.param(("", "/fr-fra/x", "h.org", "en"), False, False, id="path-subtag-three-letters"),
        pytest.param(("", "/abc/x", "h.org", "en"), False, True, id="path-three-letters-not-marker"),
        pytest.param(("", "/en-u1/x", "h.org", "en"), False, True, id="path-subtag-not-letters"),
        pytest.param(("", "/e1/x", "h.org", "en"), False, True, id="path-second-char-not-letter"),
        pytest.param(("lang=de", "/x", "h.org", "en"), False, False, id="query-lang-other-language"),
        pytest.param(("lang=en-gb", "/x", "h.org", "en"), False, True, id="query-lang-prefix-matches"),
        pytest.param(("lang=", "/x", "h.org", "en"), False, True, id="query-lang-empty-value"),
        pytest.param(("", "/x", "de.example.org", "en"), True, False, id="strict-host-other-language"),
        pytest.param(("", "/x", "de.example.org", "en"), False, True, id="non-strict-ignores-host"),
        pytest.param(("", "/x", "en.example.org", "en"), True, True, id="strict-host-same-language"),
        pytest.param(("", "/x", "abc.example.org", "en"), True, True, id="strict-host-label-not-two-letters"),
        pytest.param(("", "/x", "de", "en"), True, False, id="strict-dotless-host-label"),
        pytest.param(("", "/enxab/x", "h.org", "en"), False, True, id="path-five-chars-no-separator"),
    ],
)
def test_language_matches_cases(markers: tuple[str, str, str, str], *, strict: bool, expected: bool) -> None:
    query, path, hostname, language = markers
    assert _url_language_matches(query, path, hostname, language, strict, _LANGUAGE_PARAMS, _ISO) is expected


def test_language_matches_rejects_missing_arguments() -> None:
    lax = False
    with pytest.raises(TypeError):
        _url_language_matches("", "/x", "h.org", "en", lax)  # ty: ignore[missing-argument]
