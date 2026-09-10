from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Markdown, parse


@pytest.mark.parametrize("count", [1, 10, 1000], ids=["one", "ten", "thousand"])
def test_markdown_repeated_escapes(count: int) -> None:
    assert parse(f"<p>{'*' * count}</p>").to_markdown() == r"\*" * count


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param("<p>aa <em>***</em> zz</p>", "aa\n*\\*\\*\\**\nzz", id="deferred-emphasis"),
        pytest.param("<p>aa *** zz</p>", "aa\n\\*\\*\\*\nzz", id="escaped-word"),
        pytest.param("<p>  *** zz</p>", "\\*\\*\\*\nzz", id="leading-whitespace"),
        pytest.param("<p>aa café zz</p>", "aa\ncafe\nzz", id="transliteration"),
    ],
)
def test_markdown_escaped_word_wrapping(html: str, expected: str) -> None:
    config: Final = Markdown(wrapping=Markdown.Wrapping(width=5), document=Markdown.Document(transliterate=True))
    assert parse(html).to_markdown(config) == expected
