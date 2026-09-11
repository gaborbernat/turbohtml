from __future__ import annotations

from typing import Final

import pytest

from turbohtml.extract import feed


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param(
            "<dc:creator>creator</dc:creator><author>author</author><content>plain</content>"
            "<content:encoded>encoded</content:encoded><dc:description>dc</dc:description>"
            "<description>description</description><summary>summary</summary><dc:date>dc-date</dc:date>"
            "<pubdate>pubdate</pubdate><published>published</published><lastbuilddate>last</lastbuilddate>"
            '<updated>updated</updated><id>id</id><guid isPermaLink="false">guid</guid><title>title</title>',
            ("title", None, "guid", "updated", "published", "summary", "encoded", "author"),
            id="field-name-precedence",
        ),
        pytest.param(
            "<title> </title><title>later</title><summary></summary><summary>later</summary>"
            "<description>fallback</description>",
            (None, None, None, None, None, "fallback", None, None),
            id="first-empty-occurrence",
        ),
        pytest.param(
            "<guid></guid><guid>later</guid><id>identifier</id>",
            (None, None, "identifier", None, None, None, None, None),
            id="first-guid-controls-fallback",
        ),
        pytest.param(
            '<link href="self" rel="self"/><link href="first" rel="alternate"/><link href="second"/>',
            (None, "first", None, None, None, None, None, None),
            id="first-alternate-link",
        ),
        pytest.param(
            '<link>rss-link</link><link href="alternate" rel="alternate"/>',
            (None, "rss-link", None, None, None, None, None, None),
            id="rss-text-before-atom-link",
        ),
        pytest.param(
            "<author><name></name>ignored</author><author>later</author><dc:creator>creator</dc:creator>",
            (None, None, None, None, None, None, None, "creator"),
            id="nested-empty-author-name",
        ),
        pytest.param(
            "text<!--comment--><extension><title>nested</title></extension><updatxx>fake</updatxx>"
            "<xxxxxxx>ignored</xxxxxxx><x>ignored</x><title>direct</title>",
            ("direct", None, None, None, None, None, None, None),
            id="only-direct-exact-tags",
        ),
    ],
)
def test_entry_field_precedence(fields: str, expected: tuple[str | None, ...]) -> None:
    result: Final = feed(f"<rss><channel><item>{fields}</item></channel></rss>")
    assert result is not None
    assert result.entries == (expected,)


def test_feed_empty_metadata_uses_fallback() -> None:
    assert feed(
        "<rss><channel><title> </title><description> </description><subtitle>fallback</subtitle>"
        "<updated> </updated><lastbuilddate>date</lastbuilddate></channel></rss>"
    ) == ("rss", None, None, "fallback", "date", ())
