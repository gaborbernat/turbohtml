"""Shared fixtures: the tokenizer core is stamped once per PyUnicode storage
width, so width-sensitive tests run under all three kinds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import pytest

from turbohtml import Element, Node, parse

if TYPE_CHECKING:
    from collections.abc import Callable

_N = TypeVar("_N", bound=Node)


@pytest.fixture(params=[1, 2, 4], ids=["ucs1", "ucs2", "ucs4"])
def storage_kind(request: pytest.FixtureRequest) -> int:
    """Forced input-buffer width for the private _tokenize_states hook."""
    return request.param


@pytest.fixture(params=["", "ő", "🎉"], ids=["ucs1", "ucs2", "ucs4"])
def width_prefix(request: pytest.FixtureRequest) -> str:
    """Leading text that forces public-API input into each storage width."""
    return request.param


@pytest.fixture
def find() -> Callable[[str, str], Element]:
    """Parse html and return the first element matching selector (never None)."""

    def _find(html: str, selector: str) -> Element:
        element = parse(html).find(selector)
        assert element is not None, f"no <{selector}> in {html!r}"
        return element

    return _find


@pytest.fixture
def first() -> Callable[[str, type[_N]], _N]:
    """Parse html and return its first descendant of the given node type."""

    def _first(html: str, node_type: type[_N]) -> _N:
        return next(n for n in parse(html).descendants if isinstance(n, node_type))

    return _first
