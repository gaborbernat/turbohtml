"""Conformance tests for the C ``_url_is_tracker`` behind :func:`turbohtml.extract.normalize_url`.

``_url_is_tracker`` classifies a lowercased query-parameter name as a referral marker (an exact name, a known prefix, a
``clid`` suffix, or a tracking word between underscores) rather than content. The coverage is a differential against the
compiled vocabulary the Python cleaner used before the port, plus the boundary cases that reach each rule.
"""

from __future__ import annotations

import itertools
import re

import pytest

from turbohtml._html import _url_is_tracker

_TRACKER_NAMES = frozenset({
    "clickid",
    "dclid",
    "efid",
    "epik",
    "fb_ref",
    "fb_source",
    "fbclid",
    "gbraid",
    "gclid",
    "gclsrc",
    "igsh",
    "igshid",
    "mkt_tok",
    "msclkid",
    "partnerid",
    "s_cid",
    "sc_cid",
    "ttclid",
    "twclid",
    "wbraid",
    "wickedid",
    "yclid",
    "ysclid",
})
_TRACKER_PREFIXES = ("ad_", "ads_", "ga_", "gs_", "hsa_", "itm_", "mc_", "mtm_", "oly_", "pk_", "utm_", "vero_")
_TRACKER_WORDS = re.compile(
    r"(?:^|_)(?:aff(?:i(?:liate)?)?|campaign|cl?id|keyword|kwd|medium|refer(?:r?er)?|ref|session|source|uid|xtor)(?:_|$)"
)


def _oracle(key: str) -> bool:
    return (
        key in _TRACKER_NAMES
        or key.startswith(_TRACKER_PREFIXES)
        or key.endswith("clid")
        or _TRACKER_WORDS.search(key) is not None
    )


def _corpus() -> list[str]:
    seen = (
        set(_TRACKER_NAMES)
        | set(_TRACKER_PREFIXES)
        | {
            "",
            "id",
            "page",
            "myclid",
            "reference",
            "x_ref_y",
            "campaign",
            "affiliate",
            "xtor",
            "referer",
            "referrer",
            "utm_source",
            "ad_id",
            "a_uid_b",
            "keyword",
            "kwd",
            "medium",
            "session",
            "cid",
            "clid",
            "not_a_ref",
        }
    )
    fragments = ("utm", "ref", "id", "clid", "aff", "source", "_", "campaign", "uid")
    for length in range(4):
        seen.update("".join(combo) for combo in itertools.product(fragments, repeat=length))
    return sorted(seen)


def test_is_tracker_matches_oracle_over_corpus() -> None:
    for key in _corpus():
        assert _url_is_tracker(key) == _oracle(key), repr(key)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        pytest.param("gclid", True, id="exact-name"),
        pytest.param("utm_source", True, id="known-prefix"),
        pytest.param("myclid", True, id="clid-suffix-not-exact"),
        pytest.param("x_ref_y", True, id="tracking-word-between-underscores"),
        pytest.param("campaign", True, id="tracking-word-whole"),
        pytest.param("reference", False, id="longer-word-not-matched"),
        pytest.param("id", False, id="content-name"),
        pytest.param("", False, id="empty"),
    ],
)
def test_is_tracker_cases(key: str, *, expected: bool) -> None:
    assert _url_is_tracker(key) is expected


def test_is_tracker_rejects_non_str() -> None:
    with pytest.raises(TypeError, match="must be str"):
        _url_is_tracker(123)  # ty: ignore[invalid-argument-type]  # a non-str exercises the TypeError guard


def test_is_tracker_lone_surrogate_raises() -> None:
    # a lone-surrogate key has no UTF-8 form, so it cannot be classified and the UnicodeEncodeError propagates
    with pytest.raises(UnicodeEncodeError):
        _url_is_tracker("\ud800clid")
