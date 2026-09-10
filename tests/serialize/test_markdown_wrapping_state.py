from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element, Markdown, parse


@pytest.mark.parametrize("width", [80, 8192], ids=["ordinary", "wide"])
def test_markdown_many_words_wrap_at_requested_width(width: int) -> None:
    words: Final = ["aa"] * 10_000
    per_line: Final = (width + 1) // 3
    expected: Final = "\n".join(" ".join(words[start : start + per_line]) for start in range(0, len(words), per_line))
    assert (
        parse("<p>" + " ".join(words) + "</p>").to_markdown(Markdown(wrapping=Markdown.Wrapping(width=width)))
        == expected
    )


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param("<p>aa bb cc</p><p>dd ee ff</p>", "aa bb\ncc\n\ndd ee\nff", id="paragraphs"),
        pytest.param(
            "<p>aa bb cc</p><table><tr><td>dd ee</td></tr></table><p>ff gg hh</p>",
            "aa bb\ncc\n\n| dd ee | \n| --- | \n\nff gg\nhh",
            id="table-buffer",
        ),
    ],
)
def test_markdown_wrapping_after_blocks(html: str, expected: str) -> None:
    assert parse(html).to_markdown(Markdown(wrapping=Markdown.Wrapping(width=5))) == expected


def test_markdown_wrapping_after_converter_content() -> None:
    config: Final = Markdown(wrapping=Markdown.Wrapping(width=5), converters={"span": _keep_content})
    assert parse("<p>aa bb <span>cc dd ee</span>! ff gg</p>").to_markdown(config) == "aa bb\ncc dd\nee!\nff gg"


def _keep_content(_element: Element, content: str) -> str:
    return content
