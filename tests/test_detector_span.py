from __future__ import annotations

import pytest

from turbohtml.linkify import LinkSpan


def test_repr_shows_offsets_and_url() -> None:
    span = LinkSpan(0, 3, "abc", "http://abc", False)
    assert repr(span) == "LinkSpan(start=0, end=3, text='abc', url='http://abc')"


def test_equal_spans_compare_equal() -> None:
    left = LinkSpan(0, 3, "abc", "http://abc", False)
    right = LinkSpan(0, 3, "abc", "http://abc", False)
    assert left == right


def test_spans_differing_in_a_field_are_unequal() -> None:
    left = LinkSpan(0, 3, "abc", "http://abc", False)
    right = LinkSpan(0, 3, "abc", "https://abc", False)
    assert left != right


def test_span_compared_to_other_type_is_not_equal() -> None:
    span = LinkSpan(0, 3, "abc", "http://abc", False)
    assert span != "abc"
    assert (span == "abc") is False


def test_span_is_unhashable() -> None:
    with pytest.raises(TypeError):
        hash(LinkSpan(0, 3, "abc", "http://abc", False))
