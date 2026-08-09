"""JustHTML: parse, query, mutate, sanitize, and serialize its Python DOM."""

from __future__ import annotations

import functools
from typing import cast
from urllib.parse import urljoin

from justhtml import Element, JustHTML, Node, matches
from justhtml.parser.context import FragmentContext
from justhtml.transforms import Linkify

from bench.timing import Mutating

REQUIREMENTS = ("justhtml>=3.11",)

_LINKS_BASE = "https://example.com/base/"
_STRIP_SELECTOR = "code, a, q"


def parse(text: str) -> None:
    """Parse a whole document without JustHTML's default sanitizer."""
    JustHTML(text, sanitize=False)


def fragment(text: str) -> None:
    """Parse a fragment in a tbody context."""
    JustHTML(text, sanitize=False, fragment_context=FragmentContext("tbody"))


@functools.cache
def _parsed(text: str) -> Node:
    """Return a raw document cached for read-only operations."""
    return JustHTML(text, sanitize=False).root


def _fresh(text: str) -> Node:
    """Return a raw document for an operation that mutates its tree."""
    return JustHTML(text, sanitize=False).root


def _elements(root: Node, selector: str) -> list[Element]:
    return cast("list[Element]", root.query(selector))


def find(text: str) -> None:
    """Collect every anchor through JustHTML's selector query."""
    _parsed(text).query("a")


def select(text: str) -> None:
    """Select anchors with an href below a div."""
    _parsed(text).query("div a[href]")


def match(text: str) -> None:
    """Test every anchor against the shared selector."""
    for anchor in _elements(_parsed(text), "a"):
        matches(anchor, "div a[href]")


def text_content(text: str) -> None:
    """Collect unmodified descendant text without inserted separators."""
    _parsed(text).to_text(separator="", strip=False)


def serialize(text: str) -> None:
    """Serialize a cached raw document to compact HTML."""
    _parsed(text).to_html(pretty=False)


def navigate(text: str) -> None:
    """Walk every node in document order through JustHTML's child lists."""
    stack = [_parsed(text)]
    while stack:
        node = stack.pop()
        if node.children:
            stack.extend(reversed(node.children))


def links_extract(text: str) -> None:
    """Collect every anchor href."""
    _ = [anchor.attrs.get("href") for anchor in _elements(_parsed(text), "a")]


def links_rewrite(text: str) -> None:
    """Apply an identity rewrite to every href on the cached tree."""
    for anchor in _elements(_parsed(text), "a[href]"):
        anchor.attrs["href"] = anchor.attrs["href"]


def links_filter(text: str) -> None:
    """Resolve and deduplicate non-empty hrefs from a freshly parsed document."""
    seen: dict[str, None] = {}
    for anchor in _elements(_fresh(text), "a[href]"):
        if href := anchor.attrs.get("href"):
            seen[urljoin(_LINKS_BASE, href)] = None
    _ = list(seen)


def extract_attr(text: str) -> None:
    """Read each selected anchor's href."""
    for anchor in _elements(_parsed(text), "a"):
        anchor.attrs.get("href")


def extract_text(text: str) -> None:
    """Read each selected anchor's descendant text."""
    for anchor in _elements(_parsed(text), "a"):
        anchor.to_text(separator="", strip=False)


def class_edit(text: str) -> None:
    """Add and remove a class while restoring the cached tree."""
    for anchor in _elements(_parsed(text), "a"):
        original = anchor.attrs.get("class")
        anchor.attrs["class"] = f"{original or ''} seen".strip()
        if original is None:
            del anchor.attrs["class"]
        else:
            anchor.attrs["class"] = original


def strip_remove(text: str) -> None:
    """Drop each code, anchor, and quote subtree, then serialize."""
    root = _fresh(text)
    for node in _elements(root, _STRIP_SELECTOR):
        if node.parent is not None:
            node.parent.remove_child(node)
    root.to_html(pretty=False)


def strip_tags(text: str) -> None:
    """Unwrap each code, anchor, and quote element, then serialize."""
    root = _fresh(text)
    for node in reversed(_elements(root, _STRIP_SELECTOR)):
        if (parent := node.parent) is not None:
            for child in list(node.children):
                parent.insert_before(child, node)
            parent.remove_child(node)
    root.to_html(pretty=False)


def socialcard(text: str) -> None:
    """Read OpenGraph-style property and content attributes."""
    for meta in _elements(_fresh(text), "meta"):
        meta.attrs.get("property")
        meta.attrs.get("content")


def extract_url(case: tuple[str, str]) -> None:
    """Read the base href or meta-refresh content from a fresh document."""
    kind, text = case
    root = _fresh(text)
    if kind == "base":
        if (base := root.query_one("base")) is not None:
            cast("Element", base).attrs.get("href")
    elif (refresh := root.query_one("meta[http-equiv=refresh]")) is not None:
        cast("Element", refresh).attrs.get("content")


def sanitize(text: str) -> None:
    """Parse with JustHTML's default sanitizer and serialize its result."""
    JustHTML(text).root.to_html(pretty=False)


def linkify(text: str) -> None:
    """Auto-link URLs and emails while parsing, then serialize the transformed tree."""
    JustHTML(text, sanitize=False, transforms=[Linkify()]).root.to_html(pretty=False)


def markdown(case: tuple[str, str]) -> None:
    """Convert HTML to Markdown; JustHTML does not expose turbohtml's configured options."""
    _kind, text = case
    _parsed(text).to_markdown()


def edit(root: Node) -> None:
    """Set rel=nofollow on every anchor in a fresh tree."""
    for anchor in _elements(root, "a"):
        anchor.attrs["rel"] = "nofollow"


def links_absolutize(root: Node) -> None:
    """Resolve every href against the shared base URL."""
    for anchor in _elements(root, "a"):
        if (href := anchor.attrs.get("href")) is not None:
            anchor.attrs["href"] = urljoin(_LINKS_BASE, href)


OPERATIONS = {
    "parse": (parse, "JustHTML"),
    "fragment": (fragment, "JustHTML"),
    "find": (find, "JustHTML"),
    "select": (select, "JustHTML"),
    "match": (match, "JustHTML"),
    "text-content": (text_content, "JustHTML"),
    "serialize": (serialize, "JustHTML"),
    "navigate": (navigate, "JustHTML"),
    "links-extract": (links_extract, "JustHTML"),
    "links-rewrite": (links_rewrite, "JustHTML"),
    "links-filter": (links_filter, "JustHTML"),
    "extract-attr": (extract_attr, "JustHTML"),
    "extract-text": (extract_text, "JustHTML"),
    "class-edit": (class_edit, "JustHTML"),
    "strip-remove": (strip_remove, "JustHTML"),
    "strip-tags": (strip_tags, "JustHTML"),
    "socialcard": (socialcard, "JustHTML"),
    "extract-url": (extract_url, "JustHTML"),
    "sanitize": (sanitize, "JustHTML"),
    "linkify": (linkify, "JustHTML"),
    "markdown": (markdown, "JustHTML"),
    "edit": (Mutating(_fresh, edit), "JustHTML"),
    "links-absolutize": (Mutating(_fresh, links_absolutize), "JustHTML"),
}

__all__ = ["OPERATIONS", "REQUIREMENTS"]
