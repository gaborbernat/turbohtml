#!/usr/bin/env python3
"""
Benchmark turbohtml's escape/unescape against the standard library.

Run with ``tox -e bench``. Timing uses the minimum of many trials, which filters
out scheduler/thermal noise (noise only ever makes a run slower). Pass a substring
as a positional argument to run only matching cases.
"""

from __future__ import annotations

import html
import sys
import time
from typing import TYPE_CHECKING

import turbohtml

if TYPE_CHECKING:
    from collections.abc import Callable

CASES: list[tuple[str, str, str]] = [
    ("escape", "plain prose, no specials", "the quick brown fox jumps over the lazy dog " * 80),
    ("escape", "typical HTML markup", '<p>Tom & Jerry said "hi" to <b>O\'Brien</b> & co.</p> ' * 60),
    ("escape", "special-dense", "<>&\"'" * 500),
    ("escape", "non-ASCII prose (UCS-2)", "résumé café naïve Москва " * 120),
    ("escape", "astral text (UCS-4)", "emoji \U0001f600 party \U0001f389 " * 120),
    ("unescape", "named references (dense)", "&amp;&lt;&gt;&quot;&copy;&mdash;&eacute; " * 60),
    ("unescape", "numeric references (dense)", "&#62;&#x3e;&#38;&#127881;&#x1F600; " * 60),
    ("unescape", "mixed named + numeric", "Tom &amp; Jerry &mdash; caf&eacute; &#127881; &lt;b&gt; " * 30),
    ("unescape", "prose, sparse references", ("the quick brown fox " * 20 + "&amp; ") * 12),
    ("unescape", "non-ASCII with references", "café &amp; résumé &copy; Москва &mdash; " * 60),
]


def best(func: Callable[[str], str], arg: str) -> float:
    """Return the fastest per-call time over many trials (noise-resistant)."""
    inner = 1
    while True:
        start = time.perf_counter()
        for _ in range(inner):
            func(arg)
        if time.perf_counter() - start > 0.005:
            break
        inner *= 2
    fastest = float("inf")
    for _ in range(50):
        start = time.perf_counter()
        for _ in range(inner):
            func(arg)
        fastest = min(fastest, (time.perf_counter() - start) / inner)
    return fastest


def main() -> None:
    """Print a turbohtml-vs-stdlib timing table."""
    selector = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"{'operation':10} {'input':28} {'turbohtml':>11} {'stdlib':>10} {'speedup':>8}")
    for op, name, arg in CASES:
        if selector and selector not in op and selector not in name:
            continue
        turbo = best(getattr(turbohtml, op), arg)
        stdlib = best(getattr(html, op), arg)
        print(f"{op:10} {name:28} {turbo * 1e6:8.2f} us {stdlib * 1e6:8.2f} us {stdlib / turbo:6.1f}x")


if __name__ == "__main__":
    main()
