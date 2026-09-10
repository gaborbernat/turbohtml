from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element


@pytest.mark.parametrize("mode", ["open", "closed"])
@pytest.mark.parametrize(
    ("light", "shadow", "expected"),
    [
        pytest.param(
            "",
            '<slot name="a">first</slot><slot name="b">second</slot>',
            ["first", "second"],
            id="empty-host",
        ),
        pytest.param(
            '<b slot="b">one</b><i slot="a">two</i><u slot="b">three</u>',
            '<slot name="a"></slot><slot name="b"></slot>',
            ['<i slot="a">two</i>', '<b slot="b">one</b>', '<u slot="b">three</u>'],
            id="host-order",
        ),
        pytest.param(
            '<b slot="a">one</b>',
            '<slot name="a"></slot><slot name="a">fallback</slot><slot name="a">last</slot>',
            ['<b slot="a">one</b>', "fallback", "last"],
            id="duplicate-first-wins",
        ),
        pytest.param(
            '<b slot="a">one</b>',
            '<section><slot name="a"></slot></section><slot name="a">fallback</slot><slot name="a">last</slot>',
            ['<section><slot name="a"></slot></section>', "fallback", "last"],
            id="first-slot-nested",
        ),
        pytest.param(
            '<!--ignore-->text<b>one</b><i slot="">two</i><u slot="absent">three</u>',
            '<slot name="absent"></slot><slot name>fallback</slot><slot name="">duplicate</slot>',
            ['<u slot="absent">three</u>', "text", "<b>one</b>", '<i slot="">two</i>', "duplicate"],
            id="default-name-and-text",
        ),
        pytest.param(
            '<b slot="é">one</b><i slot="水">two</i><u slot="🦀">three</u>',
            '<slot name="é"></slot><slot name="🦀"></slot><slot name="水"></slot>',
            ['<b slot="é">one</b>', '<u slot="🦀">three</u>', '<i slot="水">two</i>'],
            id="unicode-names",
        ),
        pytest.param(
            '<b slot="missing">one</b>',
            '<slot name="first">first</slot><slot name="second"><slot name="third">nested</slot></slot>',
            ["first", "nested"],
            id="unmatched-nested-fallback",
        ),
    ],
)
def test_flattened_assignment_order(mode: str, light: str, shadow: str, expected: list[str]) -> None:
    host: Final = Element("div")
    host.set_inner_html(light)
    root: Final = host.attach_shadow(mode)
    root.set_inner_html(shadow)
    assert [node.serialize() for node in host.flattened_children] == expected


def test_flattened_assignment_updates_after_edit() -> None:
    host: Final = Element("div")
    host.set_inner_html('<b slot="a">one</b><i slot="b">two</i>')
    root: Final = host.attach_shadow()
    root.set_inner_html('<slot name="a"></slot><slot name="b"></slot>')
    before: Final = host.flattened_children
    host.set_inner_html('<u slot="b">new</u>')
    root.set_inner_html('<slot name="b"></slot><slot name="a">fallback</slot>')
    assert (
        [node.serialize() for node in before],
        [node.serialize() for node in host.flattened_children],
    ) == (['<b slot="a">one</b>', '<i slot="b">two</i>'], ['<u slot="b">new</u>', "fallback"])


def test_flattened_assignment_many_names() -> None:
    host: Final = Element("div")
    host.set_inner_html("".join(f'<i slot="name-{index}">{index}</i>' for index in range(1000)))
    root: Final = host.attach_shadow()
    root.set_inner_html("".join(f'<slot name="name-{index}">fallback</slot>' for index in reversed(range(1000))))
    assert [node.text for node in host.flattened_children] == [str(index) for index in reversed(range(1000))]
