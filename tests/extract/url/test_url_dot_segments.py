"""Conformance tests for the C ``_url_remove_dot_segments`` behind :func:`turbohtml.extract.normalize_url`.

The resolver drops ``.`` segments and pops the parent for ``..`` segments, reading each segment's ``%2e``/``%2E``
escapes as dots the way the WHATWG path state does (spec 4.4). A path with no ``.`` or ``%`` resolves to itself. The
cases reach each branch: the literal and both escape spellings, a three-dot segment that is not a dot segment, the
trailing dot form, and the non-dotted fast path.
"""

from __future__ import annotations

import pytest

from turbohtml._html import _url_remove_dot_segments


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        pytest.param("/a/b", "/a/b", id="no-dot-segments"),
        pytest.param("no-percent-no-dot", "no-percent-no-dot", id="fast-path-unchanged"),
        pytest.param("a.b/c", "a.b/c", id="dot-inside-segment-kept"),
        pytest.param("/a/./b", "/a/b", id="single-dot-dropped"),
        pytest.param("/a/../b", "/b", id="double-dot-pops-parent"),
        pytest.param("/a/%2e/b", "/a/b", id="percent-2e-lower-is-dot"),
        pytest.param("/a/%2E/b", "/a/b", id="percent-2e-upper-is-dot"),
        pytest.param("/a/%2E./b", "/b", id="mixed-escape-and-literal-is-dotdot"),
        pytest.param("/%2e%2e/b", "/b", id="escaped-dotdot-pops"),
        pytest.param("/a/.../b", "/a/.../b", id="three-dots-not-a-dot-segment"),
        pytest.param("/a/%2f/b", "/a/%2f/b", id="escape-not-2e-third-char"),
        pytest.param("/a/%3e/b", "/a/%3e/b", id="escape-not-2e-second-char"),
        pytest.param("/a/%2/b", "/a/%2/b", id="escape-too-short-for-2e"),
        pytest.param("/a/.", "/a/", id="trailing-single-dot"),
        pytest.param("/a/..", "/", id="trailing-double-dot"),
        pytest.param("%2E", "", id="lone-escaped-dot"),
    ],
)
def test_remove_dot_segments_cases(path: str, expected: str) -> None:
    assert _url_remove_dot_segments(path) == expected


def test_remove_dot_segments_rejects_non_str() -> None:
    with pytest.raises(TypeError, match="must be str"):
        _url_remove_dot_segments(123)  # ty: ignore[invalid-argument-type]  # a non-str exercises the TypeError guard
