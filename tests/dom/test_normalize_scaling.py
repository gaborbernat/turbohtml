from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Comment, Element, Text


@pytest.mark.parametrize("count", [pytest.param(2, id="pair"), pytest.param(100, id="long-run")])
@pytest.mark.parametrize("text", [pytest.param("word", id="ascii"), pytest.param("é水😀", id="unicode")])
def test_normalize_keeps_first_text_and_detaches_merged_nodes(count: int, text: str) -> None:
    root: Final = Element("p")
    root.extend(Text(text) for _ in range(count))
    children: Final = tuple(root)
    root.normalize()
    assert (tuple(root), children[0].text, [(child.parent, child.text) for child in children[1:]]) == (
        (children[0],),
        text * count,
        [(None, text)] * (count - 1),
    )


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        pytest.param(("", "", ""), [], id="empty"),
        pytest.param(("a", "", ""), ["a"], id="empty-tail"),
        pytest.param(("a", "", "b"), ["ab"], id="empty-middle"),
        pytest.param(("", "a", "b"), ["ab"], id="empty-prefix"),
    ],
)
def test_normalize_removes_empty_nodes(texts: tuple[str, ...], expected: list[str]) -> None:
    root: Final = Element("p")
    root.extend(Text(text) for text in texts)
    root.normalize()
    assert [child.text for child in root] == expected


def test_normalize_preserves_separate_runs() -> None:
    root: Final = Element("p")
    root.extend([Text("a"), Text("b"), Comment("boundary"), Text("c"), Text("d")])
    root.normalize()
    assert [(type(child), child.html) for child in root] == [(Text, "ab"), (Comment, "<!--boundary-->"), (Text, "cd")]
