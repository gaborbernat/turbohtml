from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element, ShadowRoot


@pytest.mark.parametrize("mode", [pytest.param("open", id="open"), pytest.param("closed", id="closed")])
def test_late_slot_collects_children_in_order(mode: str) -> None:
    host: Final[Element] = Element("div")
    host.set_inner_html(
        "<!--before-->" + "<!--between-->".join(f'<span slot="target">{index}</span>' for index in range(64))
    )
    root: Final[ShadowRoot] = host.attach_shadow(mode)
    root.set_inner_html('<slot name="unused"></slot>' * 64 + '<slot name="target"></slot>')
    assert root.select('slot[name="target"]')[0].assigned_nodes() == host.select("span")


def test_renaming_first_slot_reassigns_children() -> None:
    host: Final[Element] = Element("div")
    host.set_inner_html('<span slot="target">a</span><b slot="other">b</b>')
    root: Final[ShadowRoot] = host.attach_shadow("open")
    root.set_inner_html('<slot name="target"></slot><slot name="target"></slot>')
    first, second = root.select("slot")
    before: Final = (first.assigned_nodes(), second.assigned_nodes())
    first.attrs["name"] = "other"
    assert (before, first.assigned_nodes(), second.assigned_nodes()) == (
        ([host.children[0]], []),
        [host.children[1]],
        [host.children[0]],
    )


def test_editing_child_slot_reassigns_children() -> None:
    host: Final[Element] = Element("div")
    host.set_inner_html('<span slot="target">a</span>')
    root: Final[ShadowRoot] = host.attach_shadow("open")
    root.set_inner_html('<slot name="target"></slot><slot></slot>')
    named, default = root.select("slot")
    before: Final = named.assigned_nodes()
    del host.select("span")[0].attrs["slot"]
    assert (before, named.assigned_nodes(), default.assigned_nodes()) == (
        [host.children[0]],
        [],
        [host.children[0]],
    )


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("", id="empty"),
        pytest.param("<!--comment-->" * 64, id="comments"),
        pytest.param('<span slot="other">value</span>', id="nonmatching"),
    ],
)
def test_unassigned_slot_keeps_fallback(content: str) -> None:
    host: Final[Element] = Element("div")
    host.set_inner_html(content)
    root: Final[ShadowRoot] = host.attach_shadow("open")
    root.set_inner_html('<slot name="other"></slot>' * 64 + '<slot name="target"><b>fallback</b></slot>')
    slot: Final[Element] = root.select('slot[name="target"]')[0]
    assert (slot.assigned_nodes(), slot.assigned_nodes(flatten=True)) == ([], slot.select("b"))
