"""Differential security oracle: the public tree equals the spec tree a browser builds.

A sanitizer keeps or drops a node by reading its tag, namespace, and attributes off the
*public* ``Element`` API (``.tag``, ``.namespace``, ``.attrs``, ``.children``). If that
public tree ever diverged from the tree a conformant browser builds for the same bytes, the
sanitizer would vet one structure while the browser renders another -- a parser-differential
bypass that no memory sanitizer can see.

``test_treebuilder_conformance`` already pins turbohtml's internal ``#document`` dump against
WPT's living tree-construction corpus. This suite closes the
remaining gap: it rebuilds the same ``#document`` dump purely from the public Element API and
asserts it matches the spec tree for every non-scripting case, document and fragment. Agreement
over the full corpus -- 570-odd cases carry a sanitizer-relevant element (script, style, foreign
content, event handlers, URL attributes) -- is the evidence that the tree a sanitizer walks is
the tree the browser resolves.

One representation gap is documented rather than silently skipped: the ``.dat`` text format wraps doctype identifiers
in unescaped quotes, so it cannot represent a quote embedded in one (``taco"`` reads back as ``taco``). turbohtml keeps
the quote, matching html5lib-python and the WHATWG tokenizer, so the public tree is asserted against turbohtml's
conformance-validated parse. See issue #478.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import turbohtml
from turbohtml import Comment, Doctype, Document, Element, Namespace, Node, ProcessingInstruction, Text, _html

if TYPE_CHECKING:
    from wpt_tree_corpus import WptHtmlTreeCase, WptHtmlTreeCorpus

# "adjust foreign attributes" (WHATWG 13.2.6.5): only these prefixed names on an SVG/MathML
# element serialize with a namespace-separating space; any other xml:/xlink: name keeps its colon.
# Bare ``xmlns`` is in the spec table but never appears on a foreign element in the pinned corpus.
_NAMESPACED_ATTRS = frozenset({
    "xlink:actuate",
    "xlink:arcrole",
    "xlink:href",
    "xlink:role",
    "xlink:show",
    "xlink:title",
    "xlink:type",
    "xml:lang",
    "xml:space",
    "xmlns:xlink",
})


def _attr_line(name: str, value: str | list[str], *, foreign: bool) -> str:
    if foreign and name in _NAMESPACED_ATTRS:
        name = name.replace(":", " ")
    if isinstance(value, list):  # the public API tokenizes class/rel into a list
        value = " ".join(value)
    return f'{name}="{value}"'


def _dump_node(node: Node, depth: int, out: list[str]) -> None:
    pad = "| " + "  " * depth
    if isinstance(node, Element):
        foreign = node.namespace is not Namespace.HTML
        prefix = f"{node.namespace.value} " if foreign else ""
        out.append(f"{pad}<{prefix}{node.tag}>")
        out.extend(
            sorted(
                "| " + "  " * (depth + 1) + _attr_line(name, value or "", foreign=foreign)
                for name, value in (node.attrs or {}).items()
            )
        )
        if not foreign and node.tag == "template":  # children hang off a "content" pseudo-node
            out.append("| " + "  " * (depth + 1) + "content")
            for child in node.children[0].children:
                _dump_node(child, depth + 2, out)
            return
        for child in node.children:
            _dump_node(child, depth + 1, out)
    elif isinstance(node, Text):
        out.append(f'{pad}"{node.data}"')
    elif isinstance(node, Comment):
        out.append(f"{pad}<!-- {node.data} -->")
    elif isinstance(node, ProcessingInstruction):
        out.append(f"{pad}<?{node.target} {node.data}?>")
    else:
        doctype = cast("Doctype", node)  # the corpus dumps only element/text/comment/doctype nodes
        name = doctype.name or ""
        if doctype.public_id is not None or doctype.system_id is not None:
            out.append(f'{pad}<!DOCTYPE {name} "{doctype.public_id or ""}" "{doctype.system_id or ""}">')
        else:
            out.append(f"{pad}<!DOCTYPE {name}>")


def _public_dump(data: str, context: str | None) -> str:
    root = turbohtml.parse_fragment(data, context) if context is not None else turbohtml.parse(data)
    out: list[str] = []
    for child in root.children:
        _dump_node(child, 0, out)
    return "\n".join(out)


def _internal_dump(data: str) -> str:
    return _html._parse_tree(data).rstrip("\n")


# The html5lib `#document` text format wraps each doctype identifier in unescaped quotes, so it cannot
# represent a quote embedded in one: `taco"` serializes to a .dat that reads back as `taco`. turbohtml
# keeps the embedded quote (matching html5lib-python and the WHATWG tokenizer), so the public tree is
# checked against turbohtml's conformance-validated parse, not the lossy .dat text. See issue #478.
_DAT_UNREPRESENTABLE: frozenset[tuple[str, str, str | None]] = frozenset({
    ("doctype01.dat", "<!DOCTYPE potato SYSTEM 'taco\"'>Hello", None),
})


def _expected(case: WptHtmlTreeCase) -> str:
    if (case["file"], case["data"], case["context"]) in _DAT_UNREPRESENTABLE:
        return _internal_dump(case["data"])
    return case["document"]


def test_public_tree_matches_spec(wpt_html_tree_corpus: WptHtmlTreeCorpus) -> None:
    cases = [case for case in wpt_html_tree_corpus["cases"] if case["scripting"] is not True]
    failures = [
        f"{case['file']}: #data {case['data']!r} (context={case['context']!r})\nexpected:\n{expected}\ngot:\n{got}"
        for case in cases
        for expected in [_expected(case)]
        for got in [_public_dump(case["data"], case["context"])]
        if got != expected
    ]
    assert not failures, f"{len(failures)}/{len(cases)} public/spec divergences\n\n" + "\n\n".join(failures[:5])


def test_corpus_exercises_sanitizer_relevant_nodes(wpt_html_tree_corpus: WptHtmlTreeCorpus) -> None:
    # a corpus edit that stops exercising the security surface (foreign content, script/style, handlers,
    # URL attributes) must fail loudly rather than let the oracle pass vacuously
    unsafe_tags = {
        "script",
        "style",
        "iframe",
        "object",
        "embed",
        "noscript",
        "noembed",
        "noframes",
        "base",
        "title",
        "template",
        "xmp",
        "plaintext",
    }
    url_attrs = {"href", "src", "action", "formaction", "poster", "cite", "xlink:href", "background"}

    def is_relevant(node: object) -> bool:
        if not isinstance(node, Element):
            return isinstance(node, Document) and any(is_relevant(child) for child in node.children)
        if node.namespace is not Namespace.HTML or (node.tag in unsafe_tags):
            return True
        attrs = node.attrs or {}
        if any(name.startswith("on") or name in url_attrs for name in attrs):
            return True
        return any(is_relevant(child) for child in node.children)

    relevant = sum(
        1
        for case in wpt_html_tree_corpus["cases"]
        if case["scripting"] is not True
        if is_relevant(
            turbohtml.parse_fragment(case["data"], context)
            if (context := case["context"]) is not None
            else turbohtml.parse(case["data"])
        )
    )
    assert relevant >= 400
