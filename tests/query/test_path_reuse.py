from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from turbohtml import Element, parse

if TYPE_CHECKING:
    from turbohtml import Document


@pytest.mark.parametrize("kind", [pytest.param("css", id="css"), pytest.param("xpath", id="xpath")])
@pytest.mark.parametrize(
    "size", [pytest.param(1, id="single"), pytest.param(2, id="pair"), pytest.param(100, id="wide")]
)
def test_paths_after_sibling_removal(kind: str, size: int) -> None:
    document: Final[Document] = parse("<ul>" + "<li>x</li><span>y</span>" * size + "</ul>")
    nodes: Final[list[Element]] = document.select("li")
    before: Final[list[str]] = [_path(node, kind) for node in nodes]
    document.remove("li:first-of-type")
    assert (before, [_path(node, kind) for node in nodes[1:]]) == (
        [_expected(kind, index, size) for index in range(1, size + 1)],
        [_expected(kind, index, size - 1) for index in range(1, size)],
    )


@pytest.mark.parametrize("kind", [pytest.param("css", id="css"), pytest.param("xpath", id="xpath")])
def test_paths_after_sibling_append(kind: str) -> None:
    document: Final[Document] = parse("<ul><li>first</li></ul>")
    before: Final[str] = _path(document.select("li")[0], kind)
    document.select("ul")[0].append(Element("li"))
    assert (before, [_path(node, kind) for node in document.select("li")]) == (
        _expected(kind, 1, 1),
        [_expected(kind, 1, 2), _expected(kind, 2, 2)],
    )


@pytest.mark.parametrize(
    ("target", "value", "expected"),
    [
        pytest.param(0, "new", "#new", id="replace-anchor"),
        pytest.param(1, "first", "html > body > p:nth-of-type(1)", id="duplicate-anchor"),
        pytest.param(0, None, "html > body > p:nth-of-type(1)", id="delete-anchor"),
    ],
)
def test_css_path_after_id_change(target: int, value: str | None, expected: str) -> None:
    document: Final[Document] = parse('<p id="first">one</p><p id="second">two</p>')
    nodes: Final[list[Element]] = document.select("p")
    before: Final[str] = nodes[0].css_path()
    if value is None:
        del nodes[target].attrs["id"]
    else:
        nodes[target].attrs["id"] = value
    assert (before, nodes[0].css_path()) == ("#first", expected)


@pytest.mark.parametrize("kind", [pytest.param("css", id="css"), pytest.param("xpath", id="xpath")])
def test_path_for_last_sibling_before_any_other_path(kind: str) -> None:
    document: Final[Document] = parse("<ul><li>a</li><span>b</span>text<li>c</li><li>d</li></ul>")
    assert _path(document.select("li")[-1], kind) == _expected(kind, 3, 3)


def test_css_path_after_duplicate_id_removal() -> None:
    document: Final[Document] = parse('<p id="same">one</p><p id="same">two</p>')
    nodes: Final[list[Element]] = document.select("p")
    before: Final[str] = nodes[0].css_path()
    del nodes[1].attrs["id"]
    assert (before, nodes[0].css_path()) == ("html > body > p:nth-of-type(1)", "#same")


def _path(node: Element, kind: str) -> str:
    return node.css_path() if kind == "css" else node.xpath_path()


def _expected(kind: str, index: int, size: int) -> str:
    if kind == "css":
        return "html > body > ul > li" + (f":nth-of-type({index})" if size > 1 else "")
    return "/html/body/ul/li" + (f"[{index}]" if size > 1 else "")
