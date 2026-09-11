from __future__ import annotations

from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml.extract import Entry, Feed, feed

_RSS: Final = Feed(
    "rss",
    "Example Engineering Blog",
    "https://blog.example/",
    "Notes from the Example engineering team.",
    "Tue, 07 Jul 2026 09:00:00 GMT",
    tuple(
        Entry(
            f"Release {index}: what changed",
            f"https://blog.example/posts/{index}",
            f"tag:blog.example,2026:{index}",
            None,
            "Tue, 07 Jul 2026 09:00:00 GMT",
            f"Short summary of release {index}.",
            f"<p>The full body of release {index}, with details.</p>",
            "A. Writer",
        )
        for index in range(30)
    ),
)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        pytest.param(0, _RSS, id="rss"),
        pytest.param(1, _RSS, id="rss-extensions"),
        pytest.param(
            2,
            Feed(
                "atom",
                "Example",
                None,
                None,
                None,
                tuple(
                    Entry(
                        f"Entry {index}",
                        f"https://example.com/{index}",
                        f"urn:{index}",
                        "2026-07-06",
                        None,
                        f"Summary {index}",
                        "Full body",
                        "Writer",
                    )
                    for index in range(30)
                ),
            ),
            id="atom",
        ),
    ],
)
def test_feed_benchmark_output(case: int, expected: Feed) -> None:
    assert feed(cast("str", INPUTS["syndication"]()[case][1])) == expected
