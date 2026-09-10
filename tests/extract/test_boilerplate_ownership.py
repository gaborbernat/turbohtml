from __future__ import annotations

import gc
from typing import TYPE_CHECKING, Final

import pytest

from turbohtml.extract import Paragraph, boilerplate

if TYPE_CHECKING:
    from types import ModuleType


@pytest.mark.parametrize(
    "wrapper", [pytest.param("", id="direct"), pytest.param("span", id="span"), pytest.param("b", id="bold")]
)
def test_boilerplate_keeps_text_after_snapshot_release(wrapper: str) -> None:
    prose: Final = "A comet passes near the Sun, warms up and releases gas, forming a glowing coma around it."
    linked: Final = '<a href="/comet">comet</a>'
    content: Final = f"<{wrapper}>{linked}</{wrapper}>" if wrapper else linked
    page: Final = f"<article><p>{prose}</p><p>Read about this {content} today.</p></article>"
    assert [paragraph.text for paragraph in boilerplate(page)] == [prose, "Read about this comet today."]


def test_boilerplate_classifies_owned_text() -> None:
    prose: Final = "A comet passes near the Sun, warms up and releases gas, forming a glowing coma around it."
    assert boilerplate(f"<article><p>{prose}</p></article>") == [
        Paragraph(text=prose, is_boilerplate=False, is_heading=False)
    ]


def test_boilerplate_releases_text_snapshots() -> None:
    # PyPy lacks tracemalloc and reclaims objects on a different schedule.
    tracing: Final[ModuleType] = pytest.importorskip("tracemalloc")
    page: Final = "<article><p>" + "A comet passes near the Sun. " * 256 + '<a href="/more">more</a></p></article>'
    tracing.start()
    try:
        for _ in range(2):
            boilerplate(page)
        gc.collect()
        before: Final = tracing.get_traced_memory()[0]
        for _ in range(128):
            boilerplate(page)
        gc.collect()
        assert tracing.get_traced_memory()[0] - before < 64 * 1024
    finally:
        tracing.stop()
