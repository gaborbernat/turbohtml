from __future__ import annotations

from typing import Final

from turbohtml import Element


def test_shadow_flatten_keeps_sibling_fallback_order() -> None:
    shadow: Final = Element("div").attach_shadow("open")
    shadow.set_inner_html("<slot>" + "".join(f"<slot>{index}</slot>" for index in range(100)) + "</slot>")
    assert [node.text for node in shadow.select("slot")[0].assigned_nodes(flatten=True)] == [
        str(index) for index in range(100)
    ]
