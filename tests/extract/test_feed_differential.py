from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml.extract import Entry, Feed, feed

_FEEDPARSER: Final = pytest.importorskip("feedparser")


@pytest.mark.parametrize("case", [0, 1, 2], ids=["rss", "rss-extensions", "atom"])
def test_feed_benchmark_entry_values(case: int) -> None:
    source: Final = cast("str", INPUTS["syndication"]()[case][1])
    oracle: Final = _FEEDPARSER.parse(source)
    entries: Final = tuple(
        Entry(
            cast("str | None", entry.get("title")),
            cast("str | None", entry.get("link")),
            cast("str | None", entry.get("id")),
            cast("str | None", entry.get("updated")),
            cast("str | None", entry.get("published")),
            cast("str | None", entry.get("summary")),
            cast("list[dict[str, str]]", entry.get("content", [{"value": ""}]))[0]["value"],
            cast("str | None", entry.get("author")),
        )
        for entry in map(dict, oracle.entries)
    )
    header: Final = dict(oracle.feed)
    assert feed(source) == Feed(
        "atom" if oracle.version.startswith("atom") else "rss",
        cast("str | None", header.get("title")),
        cast("str | None", header.get("link")),
        cast("str | None", header.get("subtitle")),
        cast("str | None", header.get("updated")),
        entries,
    )
