from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml.extract import normalize_url

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

_CASES: Final[list[ParameterSet]] = [
    pytest.param("münchen.example", "xn--mnchen-3ya.example", id="normalized"),
    pytest.param("a\u0301.example", "xn--1ca.example", id="decomposed"),
    pytest.param("q\u0301\u0323.example", "xn--q-xbb5h.example", id="reordered"),
    pytest.param("a\u0305\u0301.example", "xn--a-xbbl.example", id="blocked"),
    pytest.param("\u1100\u1161.example", "xn--o39a.example", id="hangul-lv"),
    pytest.param("\u1100\u1161\u11a8.example", "xn--p39a.example", id="hangul-lvt"),
    pytest.param("faß.example", "xn--fa-hia.example", id="nontransitional"),
    pytest.param("\uff26\uff2f\uff2f.日本", "foo.xn--wgv71a", id="mapped-label"),
    pytest.param("a\u00adb.日本", "ab.xn--wgv71a", id="ignored-character"),
    pytest.param("münchen。example", "xn--mnchen-3ya.example", id="mapped-separator"),
    pytest.param("münchen..example", "xn--mnchen-3ya..example", id="empty-interior-label"),
    pytest.param("münchen.example.", "xn--mnchen-3ya.example.", id="trailing-label"),
    pytest.param("xn--ascii-.日本", "xn--ascii-.xn--wgv71a", id="retained-ace"),
    pytest.param("xn--.日本", ".xn--wgv71a", id="empty-ace"),
    pytest.param("A\ufffdB.example", "a\ufffdb.example", id="disallowed-fallback"),
]


@pytest.mark.parametrize(("host", "expected"), _CASES)
def test_idna_shared_public_target(host: str, expected: str) -> None:
    assert normalize_url(f"https://{host}/item?q=1") == f"https://{expected}/item?q=1"
