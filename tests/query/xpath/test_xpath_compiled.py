"""Lifecycle of the precompiled :class:`turbohtml.XPath` object: threads and GC.

The compiled program holds no mutable state and no tree pointers, and evaluation guards
each tree under the handle's critical section, so one shared object can run against many
documents in parallel. It does hold Python references (the source string and the bound
extensions dict, which a callable can cycle back to), so it also participates in cyclic
garbage collection. The evaluation-semantics tests live in ``test_xpath_eval.py``.
"""

from __future__ import annotations

import gc
import sys
import threading
from typing import TYPE_CHECKING

import pytest

import turbohtml
from turbohtml import Element, XPath

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import SimpleNamespace


def test_one_compiled_expression_across_threads_each_correct() -> None:
    selector = XPath("//td[@class=$cls]")
    documents = [
        turbohtml.parse(f"<table><tr><td class='num'>{index}</td><td>x</td></tr></table>") for index in range(8)
    ]
    results: dict[int, list[str]] = {}
    lock = threading.Lock()
    start = threading.Barrier(len(documents))

    def worker(index: int) -> None:
        start.wait()
        cells = [cell.text for cell in selector(documents[index], cls="num") if isinstance(cell, Element)]
        with lock:
            results[index] = cells

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(len(documents))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == {index: [str(index)] for index in range(len(documents))}


def test_concurrent_evaluation_on_one_document_is_memory_safe() -> None:
    document = turbohtml.parse("<body>" + "".join(f"<p>{index}</p>" for index in range(100)) + "</body>")
    selector = XPath("//p")
    start = threading.Barrier(4)
    counts: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        start.wait()
        for _ in range(50):
            found = len(selector(document))
            with lock:
                counts.append(found)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert counts == [100] * 200


@pytest.mark.skipif(sys.implementation.name == "pypy", reason="PyPy's gc exposes no is_tracked")
def test_object_is_gc_tracked() -> None:
    selector = XPath("//a")
    assert gc.is_tracked(selector)


def test_collect_with_live_objects_traverses_them() -> None:
    def extension(_context: SimpleNamespace) -> str:
        return "x"

    extensions: dict[tuple[str | None, str], Callable[..., str | float | bool]] = {(None, "x"): extension}
    plain = XPath("//a")
    with_extensions = XPath("x()", extensions=extensions)
    gc.collect()
    doc = turbohtml.parse("<a>one</a>")
    assert plain(doc) == [doc.xpath_one("//a")]
    assert with_extensions(doc) == "x"


@pytest.mark.skipif(
    sys.implementation.name == "pypy",
    reason="cpyext never breaks a cycle that runs through both a C extension object and a Python one, "
    "so this cycle leaks there; see docs/explanation/interpreters.rst",
)
def test_extension_reference_cycle_is_collected() -> None:
    class Holder:
        ref: XPath | None = None

        def extension(self, _context: SimpleNamespace) -> str:
            return repr(self.ref)

    holder = Holder()
    extensions: dict[tuple[str | None, str], Callable[..., str | float | bool]] = {(None, "x"): holder.extension}
    selector = XPath("x()", extensions=extensions)
    holder.ref = selector  # selector -> extensions -> bound method -> holder -> selector
    assert selector(turbohtml.parse("<a>one</a>")) == "XPath('x()')"
    del selector
    del holder
    del extensions
    assert gc.collect() >= 0


HTML = "<html><body><div><p>a</p><p>b</p></div><a href='/x'>x</a></body></html>"


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


def tags(result: object) -> list[str]:
    assert isinstance(result, list)
    return [node.tag for node in result if isinstance(node, Element)]


def test_repeated_query_is_consistent(doc: turbohtml.Node) -> None:
    for _ in range(5):
        assert tags(doc.xpath("//p")) == ["p", "p"]


def test_move_to_front(doc: turbohtml.Node) -> None:
    # //p falls behind //a in the cache, then is queried again from a non-front slot
    doc.xpath("//p")
    doc.xpath("//a")
    assert tags(doc.xpath("//p")) == ["p", "p"]


def test_distinct_but_equal_key_hits_same_entry(doc: turbohtml.Node) -> None:
    name = "p"
    first = f"//{name}"
    second = f"//{name}"
    assert first is not second  # two distinct str objects with equal content
    doc.xpath(first)
    assert tags(doc.xpath(second)) == ["p", "p"]


def test_eviction_recompiles(doc: turbohtml.Node) -> None:
    assert tags(doc.xpath("//p")) == ["p", "p"]
    # fill past the cache capacity with distinct expressions, evicting //p
    for index in range(20):
        assert doc.xpath(f"//missing{index}") == []
    # //p was evicted; it must recompile to the same answer
    assert tags(doc.xpath("//p")) == ["p", "p"]


def test_compile_error_after_caching(doc: turbohtml.Node) -> None:
    doc.xpath("//p")  # populate the cache first
    with pytest.raises(ValueError, match="node test"):
        doc.xpath("//")
