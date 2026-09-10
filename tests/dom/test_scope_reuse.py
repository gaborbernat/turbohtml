from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse


@pytest.mark.parametrize("depth", [pytest.param(1, id="shallow"), pytest.param(256, id="deep")])
def test_scope_repeated_ignored_end_tags(depth: int) -> None:
    source: Final = "<div>" + "<span>" * depth + "before" + "</address>" * 1000 + "after" + "</span>" * depth + "</div>"
    root: Final = parse(source).find("div")
    assert root is not None
    assert (root.text, len(root.find_all("span"))) == ("beforeafter", depth)


@pytest.mark.parametrize(
    ("source", "tag", "expected"),
    [
        pytest.param("<div></address><address>inside</address>outside</div>", "address", ["inside"], id="push"),
        pytest.param(
            "<div><address>inside</address>outside</address>tail</div>", "div", ["insideoutsidetail"], id="pop"
        ),
        pytest.param("<div><span>before</address></div>after", "div", ["before"], id="different-atom"),
    ],
)
def test_scope_reuse_after_stack_changes(source: str, tag: str, expected: list[str]) -> None:
    assert [element.text for element in parse(source).find_all(tag)] == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "<b><i><p>x</b>y",
            "<html><head></head><body><b><i></i></b><i><p><b>x</b>y</p></i></body></html>",
            id="inner-adoption-clone",
        ),
        pytest.param(
            "<head></head><template><p>x</p></template><p>y</p>",
            "<html><head><template><p>x</p></template></head><body><p>y</p></body></html>",
            id="after-head-template",
        ),
    ],
)
def test_scope_stack_replacement_preserves_tree(source: str, expected: str) -> None:
    assert parse(source).serialize() == expected
