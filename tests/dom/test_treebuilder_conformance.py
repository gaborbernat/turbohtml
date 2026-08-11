"""Verify the tree builder against the WPT tree-construction suite.

The committed corpus pins WPT's living ``html/syntax/parsing/resources`` data so
upstream changes cannot alter CI without a reviewed diff. Every case TurboHTML
can execute must match its ``#document`` tree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from turbohtml import _html

if TYPE_CHECKING:
    from wpt_tree_corpus import WptHtmlTreeCase, WptHtmlTreeCorpus


def _build(case: WptHtmlTreeCase) -> str:
    if (context := case["context"]) is not None:
        return _html._parse_fragment(case["data"], context, bool(case["scripting"])).rstrip("\n")
    return _html._parse_tree(case["data"], bool(case["scripting"])).rstrip("\n")


def test_tree_construction(wpt_html_tree_corpus: WptHtmlTreeCorpus) -> None:
    exclusions = {
        (item["file"], item["data"], item["context"], item["scripting"]) for item in wpt_html_tree_corpus["exclusions"]
    }
    cases = [
        case
        for case in wpt_html_tree_corpus["cases"]
        if (case["file"], case["data"], case["context"], case["scripting"]) not in exclusions
    ]
    failures = [
        f"{case['file']}: #data {case['data']!r} (context={case['context']!r}, scripting={case['scripting']})\n"
        f"expected:\n{case['document']}\ngot:\n{_build(case)}"
        for case in cases
        if _build(case) != case["document"]
    ]
    assert not failures, f"{len(failures)}/{len(cases)} failing\n\n" + "\n\n".join(failures[:5])
