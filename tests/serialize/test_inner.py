from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Comment, Element, Html, Indent, Minify, Node, Text, parse, parse_fragment


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("<p>a<b>b</b>c</p>", "a<b>b</b>c", id="mixed"),
        pytest.param("<p></p>", "", id="empty"),
        pytest.param("<script>a < b && c</script>", "a < b && c", id="raw-text"),
        pytest.param("<pre>\n\n a</pre>", "\n a", id="leading-newline"),
        pytest.param("<template><b>x</b></template>", "<b>x</b>", id="template"),
        pytest.param("<p>a&amp;b</p>", "a&amp;b", id="escaping"),
        pytest.param("<br>", "", id="void"),
    ],
)
def test_inner_compact(source: str, expected: str) -> None:
    root: Final = parse_fragment(source).children[0]
    assert root.serialize(inner=True) == expected


@pytest.mark.parametrize("layout", [None, Indent(), Minify()])
@pytest.mark.parametrize("node", [Text("x"), Comment("x"), Element("p")])
def test_inner_empty(layout: Indent | Minify | None, node: Node) -> None:
    assert not node.serialize(Html(layout=layout), inner=True)


@pytest.mark.parametrize("layout", [None, Indent(), Minify()])
def test_inner_document(layout: Indent | Minify | None) -> None:
    root: Final = parse("<p>a</p>")
    options: Final = Html(layout=layout)
    assert root.serialize(options, inner=True) == root.serialize(options)


@pytest.mark.parametrize("tag", ["pre", "textarea", "listing", "script", "style"])
@pytest.mark.parametrize("layout", [Indent(), Minify()])
def test_inner_preserve(tag: str, layout: Indent | Minify) -> None:
    root: Final = Element(tag, children=[Text("  a\n b  ")])
    assert root.serialize(Html(layout=layout), inner=True) == "  a\n b  "


def test_inner_indent() -> None:
    root: Final = parse_fragment("<div><p>a</p><p>b</p></div>").children[0]
    assert root.serialize(Html(layout=Indent()), inner=True) == "<p>\n  a\n</p>\n<p>\n  b\n</p>"


def test_inner_minify_state() -> None:
    root: Final = Element("div", children=[Text("a "), Comment("x"), Text(" b")])
    assert root.serialize(Html(layout=Minify()), inner=True) == "a b"


def test_inner_xml() -> None:
    root: Final = parse_fragment("<p>a<br>b</p>").children[0]
    assert root.serialize(Html(xml=True), inner=True) == "a<br/>b"


@pytest.mark.parametrize("layout", [None, Indent()])
@pytest.mark.parametrize("source", ["<p>a<b>b</b>c</p>", "<script>a < b</script>", "<pre> a\n b</pre>", "<br>"])
def test_inner_iterator(layout: Indent | None, source: str) -> None:
    root: Final = parse_fragment(source).children[0]
    options: Final = Html(layout=layout)
    assert "".join(root.serialize_iter(options, inner=True)) == root.serialize(options, inner=True)


def test_inner_iterator_chunks() -> None:
    root: Final = parse_fragment("<div>" + "<p>abcdefgh</p>" * 3000 + "</div>").children[0]
    chunks: Final = tuple(root.serialize_iter(inner=True))
    assert (len(chunks) > 1, "".join(chunks)) == (True, "<p>abcdefgh</p>" * 3000)


def test_inner_iterator_rejects_minify() -> None:
    with pytest.raises(ValueError, match="cannot stream"):
        Element("p").serialize_iter(Html(layout=Minify()), inner=True)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "iso-8859-1"])
def test_inner_encode(encoding: str) -> None:
    root: Final = Element("p", children=[Text("café")])
    assert root.encode(encoding, inner=True) == "café".encode(encoding)


def test_inner_encode_error() -> None:
    with pytest.raises(UnicodeEncodeError):
        Element("p", children=[Text("é")]).encode("ascii", inner=True)


def test_inner_default_unchanged() -> None:
    assert Element("p", children=[Text("x")]).serialize() == "<p>x</p>"


def test_inner_indent_nested_preserve() -> None:
    root: Final = Element("div", children=[Element("pre", children=[Element("b", children=[Text(" a ")])])])
    assert root.serialize(Html(layout=Indent()), inner=True) == "<pre><b> a </b></pre>"


@pytest.mark.parametrize(
    ("method", "arguments"),
    [("serialize", (None, True)), ("serialize_iter", (None, True)), ("encode", ("utf-8", None, True))],
)
def test_inner_keyword_only(method: str, arguments: tuple[object, ...]) -> None:
    with pytest.raises(TypeError):
        getattr(Element("p"), method)(*arguments)


@pytest.mark.parametrize("layout", [None, Indent(), Minify()])
def test_inner_frame_ignores_children(layout: Indent | Minify | None) -> None:
    root: Final = Element("frame", children=[Text("not emitted")])
    assert not root.serialize(Html(layout=layout), inner=True)


@pytest.mark.parametrize("layout", [None, Indent(), Minify()])
@pytest.mark.parametrize("content", ["", "<title>x</title>", '<meta charset="utf-8">'])
def test_inner_meta_charset(layout: Indent | Minify | None, content: str) -> None:
    root: Final = parse(f"<head>{content}</head>").find_all("head")[0]
    result: Final = root.serialize(Html(layout=layout, meta_charset=True), inner=True)
    assert result.count("charset") == 1
    assert "<head>" not in result


def test_inner_xml_indent() -> None:
    root: Final = Element("p", children=[Element("br")])
    options: Final = Html(xml=True, layout=Indent())
    assert (root.serialize(options, inner=True), "".join(root.serialize_iter(options, inner=True))) == (
        "<br/>",
        "<br/>",
    )


@pytest.mark.parametrize("layout", [None, Indent(), Minify()])
def test_inner_foreign_context(layout: Indent | Minify | None) -> None:
    root: Final = parse_fragment("<svg><g></g></svg>").children[0]
    assert root.serialize(Html(layout=layout), inner=True) == "<g></g>"


def test_inner_metadata_on_other_context() -> None:
    root: Final = Element("div", children=[Text("x")])
    assert root.serialize(Html(layout=Indent(), meta_charset=True), inner=True) == "x"


def test_inner_minify_nested_raw_text() -> None:
    root: Final = parse_fragment("<div><script>a < b</script></div>").children[0]
    assert root.serialize(Html(layout=Minify()), inner=True) == "<script>a < b</script>"


def test_inner_shadow_root() -> None:
    root: Final = Element("div")
    shadow: Final = root.attach_shadow()
    shadow.set_inner_html("<b>  x  </b>")
    assert shadow.serialize(Html(layout=Minify()), inner=True) == "<b> x </b>"


@pytest.mark.parametrize("layout", [None, Indent()])
def test_inner_raw_context_only_applies_to_direct_text(layout: Indent | None) -> None:
    root: Final = Element("script", children=[Element("b", children=[Text("<&")])])
    assert root.serialize(Html(layout=layout), inner=True) == "<b>&lt;&amp;</b>"
