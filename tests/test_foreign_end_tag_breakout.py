"""Lock in the spec-correct handling of ``</p>``/``</br>`` end tags in foreign content.

A ``</p>`` or ``</br>`` end tag seen while the current node is an SVG/MathML element
is an "Any other end tag" in foreign content (WHATWG HTML § 13.2.6.5). The algorithm
walks up the stack of open elements; the first HTML-namespace ancestor reprocesses the
token in the current insertion mode *without popping the foreign element*. "In body"
then inserts an implied ``<p>`` (or rewrites ``</br>`` to a ``<br>`` start tag) at the
current insertion location — still *inside* the foreign root. Nothing breaks out.

The pinned ``html5lib-tests`` ``.dat`` fixtures (``tests26.dat``, ``foreign-fragment.dat``)
encode the pre-errata 2021 behavior where the implied element becomes a *sibling* of the
foreign root. That fixture is stale: html5lib's own 1.1 library, lexbor, and the literal
spec all produce containment, not breakout. These tests assert the spec-correct trees
directly so the decision survives independently of the conformance harness's overrides —
they are the standing rejection of the proposed "foreign breakout" divergence.

See https://github.com/tox-dev/turbohtml/issues/32 and
https://github.com/tox-dev/turbohtml/issues/63.
"""

from __future__ import annotations

import pytest

from turbohtml import _html

_DOCUMENT_CASES = [
    pytest.param(
        "<svg></p><foo>",
        "| <html>\n|   <head>\n|   <body>\n|     <svg svg>\n|       <p>\n|       <svg foo>",
        id="svg-end-p",
    ),
    pytest.param(
        "<svg></br><foo>",
        "| <html>\n|   <head>\n|   <body>\n|     <svg svg>\n|       <br>\n|       <svg foo>",
        id="svg-end-br",
    ),
    pytest.param(
        "<math></p><foo>",
        "| <html>\n|   <head>\n|   <body>\n|     <math math>\n|       <p>\n|       <math foo>",
        id="math-end-p",
    ),
    pytest.param(
        "<math></br><foo>",
        "| <html>\n|   <head>\n|   <body>\n|     <math math>\n|       <br>\n|       <math foo>",
        id="math-end-br",
    ),
]

_FRAGMENT_CASES = [
    pytest.param("<svg></p><foo>", "div", "| <svg svg>\n|   <p>\n|   <svg foo>", id="div-svg-end-p"),
    pytest.param("<svg></br><foo>", "div", "| <svg svg>\n|   <br>\n|   <svg foo>", id="div-svg-end-br"),
    pytest.param("</p><foo>", "svg svg", "| <svg foo>", id="svg-root-end-p"),
    pytest.param("</br><foo>", "svg svg", "| <svg foo>", id="svg-root-end-br"),
]


@pytest.mark.parametrize(("data", "expected"), _DOCUMENT_CASES)
def test_foreign_end_tag_stays_inside_root(data: str, expected: str) -> None:
    assert _html._parse_tree(data).rstrip("\n") == expected


@pytest.mark.parametrize(("data", "context", "expected"), _FRAGMENT_CASES)
def test_foreign_end_tag_in_fragment(data: str, context: str, expected: str) -> None:
    assert _html._parse_fragment(data, context).rstrip("\n") == expected
