"""Pin the output and mutation performed by the competitor benchmark adapters."""

from __future__ import annotations

import shutil
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import pytest

from turbohtml import Html, parse, parse_fragment
from turbohtml.clean import collapse_whitespace_node, strip_comments_node, transform_node

if TYPE_CHECKING:
    from collections.abc import Callable

    from bench.timing import Mutating
    from lxml.html import HtmlElement
    from selectolax.lexbor import LexborHTMLParser

_MUTATORS: Final = ("lxml", "beautifulsoup4", "beautifulsoup4_lxml", "selectolax")
_OUTPUTS: Final = (*_MUTATORS, "html5lib", "pyquery", "parsel")
_CASES: Final = (
    pytest.param("<p>a  <!--note--> b <b>c  d</b> e</p>", id="comment-tail"),
    pytest.param("<p> café\t \u03b1\n😀 &amp; &lt; &gt; \u00a0 x </p>", id="unicode-escaping"),
    pytest.param("<pre>a  b\n c</pre><textarea>d  e</textarea><p>x  y</p>", id="preserved"),
    pytest.param('<script>if (a < b) x = "  ";</script><style> a  b {}</style>', id="raw-text"),
    pytest.param("<template><p>a  <!--note--> b</p></template>", id="template"),
    pytest.param("<svg><text>a  b</text></svg><p>x  y</p>", id="foreign"),
    pytest.param("lead &amp; <br> tail <!--one--><!--two-->", id="root-text"),
    pytest.param("<p>a <!--one--> <!--two--> b</p>", id="empty-adjacent-text"),
)


@pytest.mark.parametrize("library", _MUTATORS)
@pytest.mark.parametrize("operation", ["collapse-whitespace", "strip-comments", "transform-tree"])
@pytest.mark.parametrize("fragment", _CASES)
def test_mutation(library: str, operation: str, fragment: str) -> None:
    module: Final = pytest.importorskip(f"bench.competitors.{library}", exc_type=ImportError)
    mutation: Final = cast("Mutating", module.OPERATIONS[operation][0])
    source: Final = f"<html><head></head><body>{fragment}</body></html>"
    if library == "selectolax" and "<template>" in fragment:
        with pytest.raises(ValueError, match="template contents"):
            mutation.setup(source)
        return
    tree: Final = mutation.setup(source)
    mutation.run(tree)
    if library == "lxml":
        output: Final = import_module("lxml.html").tostring(tree, encoding="unicode")
    elif library == "selectolax":
        output = cast("str", cast("LexborHTMLParser", tree).html)
    else:
        output = str(tree)
    expected: Final = parse(source)
    transform_node(
        expected,
        *{
            "collapse-whitespace": (collapse_whitespace_node,),
            "strip-comments": (strip_comments_node,),
            "transform-tree": (strip_comments_node, collapse_whitespace_node),
        }[operation],
    )
    assert parse(output).serialize(Html(sort_attributes=True)) == expected.serialize(Html(sort_attributes=True))


@pytest.mark.parametrize("library", _OUTPUTS)
@pytest.mark.parametrize("operation", ["serialize-inner", "encode-inner"])
@pytest.mark.parametrize("fragment", _CASES)
def test_inner_output(library: str, operation: str, fragment: str) -> None:
    module: Final = pytest.importorskip(f"bench.competitors.{library}", exc_type=ImportError)
    run: Final = cast("Callable[[str], str | bytes]", module.OPERATIONS[operation][0])
    output: Final = run(f"<html><head></head><body>{fragment}</body></html>")
    assert parse_fragment(output.decode() if isinstance(output, bytes) else output).serialize(
        Html(sort_attributes=True)
    ) == parse_fragment(fragment).serialize(Html(sort_attributes=True))


@pytest.mark.parametrize("library", ["lxml", "beautifulsoup4", "beautifulsoup4_lxml"])
@pytest.mark.parametrize("operation", ["serialize-inner-indent", "encode-inner-indent"])
def test_pretty_inner_output(library: str, operation: str) -> None:
    module: Final = pytest.importorskip(f"bench.competitors.{library}", exc_type=ImportError)
    run: Final = cast("Callable[[str], str | bytes]", module.OPERATIONS[operation][0])
    output: Final = run("<html><head></head><body><div><p>one</p><p>two</p></div></body></html>")
    tree: Final = parse_fragment(output.decode() if isinstance(output, bytes) else output)
    assert ([element.text.strip() for element in tree.find_all("p")], bool(tree.find_all("body"))) == (
        ["one", "two"],
        False,
    )


@pytest.mark.parametrize("operation", ["serialize-inner-minify", "encode-inner-minify"])
@pytest.mark.parametrize("fragment", _CASES[1:4])
def test_html5lib_minified_output(operation: str, fragment: str) -> None:
    module: Final = pytest.importorskip("bench.competitors.html5lib", exc_type=ImportError)
    run: Final = cast("Callable[[str], str | bytes]", module.OPERATIONS[operation][0])
    output: Final = run(f"<html><head></head><body>{fragment}</body></html>")
    expected: Final = parse_fragment(fragment)
    transform_node(expected, strip_comments_node, collapse_whitespace_node)
    assert parse_fragment(output.decode() if isinstance(output, bytes) else output).serialize() == expected.serialize()


@pytest.mark.parametrize("fragment", _CASES[:5])
def test_html5lib_whitespace_roundtrip(fragment: str) -> None:
    module: Final = pytest.importorskip("bench.competitors.html5lib", exc_type=ImportError)
    run: Final = cast("Callable[[str], str]", module.OPERATIONS["whitespace-roundtrip"][0])
    source: Final = f"<html><head></head><body>{fragment}</body></html>"
    expected: Final = parse(source)
    collapse_whitespace_node(expected)
    assert parse(run(source)).serialize() == expected.serialize()


@pytest.mark.parametrize("library", ["parse5", "jsdom"])
@pytest.mark.parametrize("operation", ["parse-inner", "parse-inner-encode"])
def test_javascript_inner_output(library: str, operation: str) -> None:
    if (
        shutil.which("node") is None
        or not (Path(__file__).parents[2] / "tools/bench/node/node_modules" / library).exists()
    ):
        pytest.skip("Node and the benchmark npm dependencies are required")
    run: Final = cast(
        "Callable[[str], str | bytes]", import_module(f"bench.competitors.{library}").OPERATIONS[operation][0]
    )
    fragment: Final = "a &amp; <b>café 😀</b><!--note--><template><p>one</p></template>"
    output: Final = run(f"<html><head></head><body>{fragment}</body></html>")
    assert (
        parse_fragment(output.decode() if isinstance(output, bytes) else output).serialize()
        == parse_fragment(fragment).serialize()
    )


@pytest.mark.parametrize(
    "fragment",
    [
        pytest.param("<p>a <!--comment--> b</p>", id="comment-boundary"),
        pytest.param("<template><p>a <!--comment--> b</p></template>", id="template-comment"),
    ],
)
def test_html5lib_minification_token_boundaries(fragment: str) -> None:
    module: Final = pytest.importorskip("bench.competitors.html5lib", exc_type=ImportError)
    run: Final = cast("Callable[[str], str]", module.OPERATIONS["serialize-inner-minify"][0])
    output: Final = parse_fragment(run(f"<html><head></head><body>{fragment}</body></html>"))
    expected: Final = parse_fragment(fragment)
    transform_node(expected, strip_comments_node, collapse_whitespace_node)
    assert (output.find_all("p")[0].text, expected.find_all("p")[0].text) == ("a  b", "a b")


@pytest.mark.parametrize("operation", ["sanitize-node", "linkify-node"])
def test_existing_node_stage_ownership(operation: str) -> None:
    module: Final = pytest.importorskip("bench.competitors.lxml_html_clean", exc_type=ImportError)
    mutation: Final = cast("Mutating", module.OPERATIONS[operation][0])
    tree: Final = cast(
        "HtmlElement", mutation.setup('<p onclick="bad()">https://example.com<script>bad()</script></p>')
    )
    output: Final = cast("HtmlElement", mutation.run(tree))
    if operation == "sanitize-node":
        assert (output is tree, len(tree.xpath(".//script")), len(output.xpath(".//script"))) == (False, 1, 0)
    else:
        assert (output is tree, output.xpath(".//a/@href")) == (True, ["https://example.com"])
