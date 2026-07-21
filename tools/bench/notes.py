"""
Why a published column does not compare like for like.

A ratio invites the reader to conclude one library is faster at the same job. For most columns that holds. For the
ones named here it does not: the party answers a different question, produces different output, or does not answer at
all, and its timing is the cost of that lesser work rather than a faster implementation. Each note says what differs
and, where it was measured, by how much, so a reader can judge the column instead of trusting or dismissing it.

Keyed by operation, then by the party label the competitor module publishes. :mod:`bench.report` writes the notes for
an operation into its feed, and the ``bench-table`` directive renders them under the table.
"""

from __future__ import annotations

from typing import Final

_STRIPPER_JS: Final = (
    "strips whitespace and comments without parsing the source, so it performs none of the renaming or structural "
    "compression the parsed minifiers do: on jQuery it emits 141.1 kB where turbohtml emits 87.8 kB"
)
_STRIPPER_CSS: Final = (
    "strips whitespace and comments without parsing, so it applies none of the color, number, and shorthand rewrites "
    "turbohtml does; on these stylesheets that leaves its output within 1.01-1.03x of turbohtml's, and 0.998x on "
    "bulma, so the structural shortenings change little on already-tight framework CSS"
)
_BUILDER: Final = (
    "concatenates a string rather than constructing a navigable tree, so nothing it builds can afterwards be queried "
    "or mutated"
)

NOTES: Final[dict[str, dict[str, str]]] = {
    "minify-js": dict.fromkeys(("rjsmin", "jsmin", "css-html-js-minify"), _STRIPPER_JS),
    "minify-css": dict.fromkeys(("rcssmin", "cssmin", "css-html-js-minify"), _STRIPPER_CSS),
    "strip-remove": {
        "w3lib": (
            "removes the tags with a regular expression over the raw string and never parses, so it cannot honor "
            "nesting or the tokenizer rules that decide where an element really ends"
        ),
    },
    "build-e": dict.fromkeys(("simple-html", "markyp", "yattag", "htbuilder", "htpy", "fast-html"), _BUILDER),
    "construct": dict.fromkeys(("simple-html", "markyp", "htbuilder", "htpy"), _BUILDER),
    "decode": {
        "stdlib": (
            "decodes with the nearest CPython codec under errors=replace, which is not the WHATWG decoder of that "
            "label: the two disagree on both the mapping tables and where decoding resumes after an error"
        ),
    },
    "linkify": {
        "lxml-html-clean": (
            "links URLs inside existing markup and never linkifies email addresses; on the prose case it produces no "
            "links at all, so that timing is the cost of finding nothing"
        ),
    },
    "date": {
        "htmldate": (
            "returns no date for the 100-candidate case, so its timing there is the cost of giving up rather than of "
            "finding the date turbohtml reports"
        ),
    },
    "text-content": {
        "resiliparse": (
            "reports about 11% fewer elements than every other parser here (876 against 989 on the mozilla page), so "
            "it collects text from a smaller tree"
        ),
    },
}
NOTES["navigate"] = {"resiliparse": NOTES["text-content"]["resiliparse"]}

__all__ = ["NOTES"]
