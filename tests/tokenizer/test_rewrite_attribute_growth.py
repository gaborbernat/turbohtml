from __future__ import annotations

from typing import Final

import pytest

from turbohtml.rewrite import Element, rewrite


@pytest.mark.parametrize(
    ("initial", "count"),
    [(0, 1), (0, 1000), (3, 17)],
    ids=["single", "many", "existing-array"],
)
def test_rewrite_attribute_growth_order(initial: int, count: int) -> None:
    def add(element: Element) -> None:
        for index in range(count):
            element.set_attribute(f"a{index}", "x")

    before: Final = "".join(f' b{index}="before"' for index in range(initial))
    after: Final = "".join(f' a{index}="x"' for index in range(count))
    assert rewrite(f"<x{before}>body</x>", elements=(("x", add),)) == f"<x{before}{after}>body</x>"


def test_rewrite_attribute_growth_remove_and_append() -> None:
    def change(element: Element) -> None:
        for index in range(17):
            element.set_attribute(f"a{index}", "before")
        for index in range(17):
            element.remove_attribute(f"a{index}")
        element.set_attribute("a0", "after")
        element.set_attribute("a1", "second")

    assert rewrite("<x>body</x>", elements=(("x", change),)) == '<x a0="after" a1="second">body</x>'


def test_rewrite_attribute_growth_replace_and_escape() -> None:
    def change(element: Element) -> None:
        for index in range(17):
            element.set_attribute(f"a{index}", "before")
        element.set_attribute("a0", '"&')

    rest: Final = "".join(f' a{index}="before"' for index in range(1, 17))
    assert rewrite("<x>body</x>", elements=(("x", change),)) == f'<x a0="&quot;&amp;"{rest}>body</x>'
