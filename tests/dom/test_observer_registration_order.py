from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element, MutationObserver


@pytest.mark.parametrize("attributes", [False, True], ids=["wrong-kind", "unrelated"])
def test_observer_overlap_keeps_old_value(*, attributes: bool) -> None:
    root: Final = Element("div")
    root.set_inner_html('<section><p data-x="before"></p></section>' + "<span></span>" * 100)
    observer: Final = MutationObserver()
    for node in root.select("span"):
        observer.observe(node, child_list=not attributes, attributes=attributes, subtree=True)
    observer.observe(root, attributes=True, subtree=True)
    observer.observe(root.select("section")[0], attributes=True, attribute_old_value=True, subtree=True)
    target: Final = root.select("p")[0]
    target.attrs["data-x"] = "after"
    assert [(record.target, record.attribute_name, record.old_value) for record in observer.take_records()] == [
        (target, "data-x", "before")
    ]
