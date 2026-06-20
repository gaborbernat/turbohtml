"""Concurrent use of IncrementalParser must stay memory-safe under free-threading.

The ``_html`` extension declares ``Py_MOD_GIL_NOT_USED``, so feed()/close() guard
the push parser's mutable C stream with a per-object critical section. Independent
parsers in parallel must each build correctly; two threads feeding one parser may
interleave unpredictably but must never crash.
"""

from __future__ import annotations

import threading

from turbohtml import IncrementalParser, parse


def test_independent_parsers_in_parallel_each_build_correctly() -> None:
    document = "<html><body>" + "".join(f"<div><p>x{index}</p></div>" for index in range(200)) + "</body></html>"
    expected = parse(document).html
    results: list[str] = []
    lock = threading.Lock()
    start = threading.Barrier(4)

    def worker() -> None:
        start.wait()
        parser = IncrementalParser()
        for position in range(0, len(document), 4):
            parser.feed(document[position : position + 4])
        with lock:
            results.append(parser.close().html)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [expected, expected, expected, expected]


def test_concurrent_feeds_on_one_parser_are_memory_safe() -> None:
    parser = IncrementalParser()
    start = threading.Barrier(2)

    def feeder(tag: str) -> None:
        start.wait()
        for index in range(200):
            parser.feed(f"<{tag}>{index}</{tag}>")

    threads = [threading.Thread(target=feeder, args=(tag,)) for tag in ("p", "span")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert isinstance(parser.close().html, str)  # interleaving is undefined, but never a crash
