from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import turbohtml
from turbohtml import Markdown

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("markup", "options"),
    [
        pytest.param("<table><td>x", Markdown(), id="table-cell"),
        pytest.param("<table><td>x", Markdown(tables=Markdown.Tables(pad=True)), id="padded-table-cell"),
        pytest.param("<table><td><blockquote>x<blockquote>y", Markdown(), id="table-cell-quote-prefix"),
        pytest.param("<ul><li>x<ul><li>", Markdown(), id="nested-list-prefix"),
        pytest.param(
            "<span><ul><li>x<ul><li>y</span>",
            Markdown(converters={"span": lambda _element, content: content}),
            id="converter-list-prefix",
        ),
    ],
)
def test_markdown_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], markup: str, options: Markdown
) -> None:
    assert set(alloc_sweep(lambda document: document.to_markdown(options), lambda: turbohtml.parse(markup))) == {
        "MemoryError"
    }
