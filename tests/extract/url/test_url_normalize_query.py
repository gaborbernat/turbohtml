"""Conformance tests for the C ``_url_normalize_query`` behind :func:`turbohtml.extract.normalize_url`.

The normalizer runs the crawl cleaner's per-pair loop: split the query on ``&``, decode and lowercase each key, drop the
denied, tracker, or non-allowlisted parameters (strict mode keeps only the content and language names), encode each
survivor for the query set, and sort them. Coverage is a differential against that Python loop across the cleaning
filter surface, plus the lone-surrogate paths that raise.
"""

from __future__ import annotations

import itertools
from functools import partial
from typing import TYPE_CHECKING

import pytest

from turbohtml._html import _url_is_tracker, _url_normalize_query, _url_percent_decode, _url_percent_encode

if TYPE_CHECKING:
    from collections.abc import Callable

_QUERY_SET = 1
_CONTENT = frozenset({"id", "page", "post", "article_id"})
_LANGUAGE = frozenset({"lang", "language"})


def _oracle(query: str, allow: frozenset[str] | None, deny: frozenset[str], *, strict: bool) -> str:
    kept: list[tuple[str, str]] = []
    for pair in query.split("&"):
        if not pair:
            continue
        key = _url_percent_decode(pair.partition("=")[0]).lower()
        if key in deny:
            continue
        if allow is not None:
            dropped = key not in allow
        elif strict:
            dropped = key not in _CONTENT and key not in _LANGUAGE
        else:
            dropped = _url_is_tracker(key)
        if dropped:
            continue
        try:
            encoded = _url_percent_encode(pair, _QUERY_SET)
        except UnicodeEncodeError as exc:
            # the retired shim converted the encoder's failure to the public ValueError; the C does the same inline
            msg = f"URL component {pair!r} has a character that cannot be percent-encoded: {exc.reason}"
            raise ValueError(msg) from exc
        kept.append((key, encoded))
    return "&".join(pair for _key, pair in sorted(kept))


def _outcome(call: Callable[[], str]) -> tuple[object, ...]:
    try:
        return ("ok", call())
    except ValueError as exc:  # UnicodeEncodeError subclasses ValueError, so a lone-surrogate failure lands here too
        return ("err", type(exc).__name__, str(exc))


_QUERIES = (
    "",
    "a=1",
    "ok=1&bad=\udcff",  # a lone surrogate cannot percent-encode, so both sides must fail identically
    "a=1&b=2",
    "b=2&a=1",
    "id=1&utm_source=x",
    "utm_campaign=z&fbclid=y&keep=1",
    "a=1&a=2&a=3",
    "=empty&x=",
    "café=1&CAFÉ=2",
    "%41=%42&ref=1",
    "lang=de&page=3",
    "session=1&content=2",
    "aff_id=1&article_id=9",
    "x=%ZZ&y=1",
    "a=1&&b=2&",
    "utm_medium=e&Id=7",
    "A=1&a=2&B=3",
    "a&b&c",
)
_ALLOWS = (None, frozenset({"id", "page"}), frozenset({"UTM_SOURCE"}), frozenset())
_DENYS = (frozenset(), frozenset({"id"}), frozenset({"a", "b"}))


def test_normalize_query_matches_oracle_over_corpus() -> None:
    for query, allow, deny, strict in itertools.product(_QUERIES, _ALLOWS, _DENYS, (False, True)):
        if strict and allow is not None:
            continue
        got = _outcome(partial(_url_normalize_query, query, allow, deny, strict, _CONTENT, _LANGUAGE))
        want = _outcome(partial(_oracle, query, allow, deny, strict=strict))
        assert got == want, (query, allow, deny, strict)


@pytest.mark.parametrize(
    ("query", "allow", "deny", "strict", "expected"),
    [
        pytest.param("b=2&a=1", None, frozenset(), False, "a=1&b=2", id="sort-non-trackers"),
        pytest.param("utm_source=x&id=1", None, frozenset(), False, "id=1", id="drop-tracker"),
        pytest.param("id=1&page=2&x=3", None, frozenset(), True, "id=1&page=2", id="strict-keeps-content"),
        pytest.param("lang=de&x=3", None, frozenset(), True, "lang=de", id="strict-keeps-language"),
        pytest.param("id=1&page=2", frozenset({"id"}), frozenset(), False, "id=1", id="allow-keeps-only-listed"),
        pytest.param("id=1&keep=2", None, frozenset({"id"}), False, "keep=2", id="deny-drops-listed"),
        pytest.param("Id=1&PAGE=2", None, frozenset(), True, "Id=1&PAGE=2", id="key-lowercased-for-filter"),
        pytest.param("", None, frozenset(), False, "", id="empty-query"),
        pytest.param("a=1&&b=2&", None, frozenset(), False, "a=1&b=2", id="empty-pairs-dropped"),
    ],
)
def test_normalize_query_cases(
    query: str, allow: frozenset[str] | None, deny: frozenset[str], expected: str, *, strict: bool
) -> None:
    assert _url_normalize_query(query, allow, deny, strict, _CONTENT, _LANGUAGE) == expected


def test_normalize_query_surrogate_key_raises() -> None:
    # a lone-surrogate key has no UTF-8 form, so the tracker test cannot classify it and the error propagates
    lax = False
    with pytest.raises(UnicodeEncodeError):
        _url_normalize_query("\ud800=1", None, frozenset(), lax, _CONTENT, _LANGUAGE)


def test_normalize_query_surrogate_value_raises() -> None:
    # the key survives, then encoding the pair fails on the surrogate value, rewrapped as the shim's ValueError
    lax = False
    with pytest.raises(ValueError, match="cannot be percent-encoded"):
        _url_normalize_query("ok=\ud800", None, frozenset(), lax, _CONTENT, _LANGUAGE)


def test_normalize_query_rejects_non_str_query() -> None:
    lax = False
    with pytest.raises(TypeError):
        _url_normalize_query(123, None, frozenset(), lax, _CONTENT, _LANGUAGE)  # ty: ignore[invalid-argument-type]


def test_normalize_query_rejects_missing_arguments() -> None:
    lax = False
    with pytest.raises(TypeError):
        _url_normalize_query("a=1", None, frozenset(), lax)  # ty: ignore[missing-argument]
