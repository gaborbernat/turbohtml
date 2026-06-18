"""Content accessors: text, data, name, namespace, and HTML serialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import Comment, Doctype, Namespace, Text, parse

if TYPE_CHECKING:
    from collections.abc import Callable

    from turbohtml import Element, Node


@pytest.mark.parametrize(
    ("html", "selector", "expected"),
    [
        pytest.param("<body><p>a<b>b</b><i>c</i></p>d</body>", "body", "abcd", id="nested-elements"),
        pytest.param("<p>a&amp;b\U0001f600c</p>", "p", "a&b\U0001f600c", id="entities-and-astral-span"),
        pytest.param("<body></body>", "body", "", id="empty"),
    ],
)
def test_text_concatenates_descendant_character_data(
    find: Callable[[str, str], Element], html: str, selector: str, expected: str
) -> None:
    assert find(html, selector).text == expected


@pytest.mark.parametrize(
    ("html", "selector", "expected"),
    [
        pytest.param("<p>x</p>", "p", "<p>x</p>", id="element"),
        pytest.param("<p class='a b'>x</p>", "p", '<p class="a b">x</p>', id="attribute-quoting"),
        pytest.param("<input disabled>", "input", '<input disabled="">', id="void-no-end-tag"),
        pytest.param("<br>", "br", "<br>", id="void-br"),
        pytest.param("<frameset><frame>", "frameset", "<frameset><frame></frameset>", id="void-frame"),
        pytest.param("<p>a<b>c</b>d</p>", "p", "<p>a<b>c</b>d</p>", id="nested"),
        pytest.param("<style>a > b { x }</style>", "style", "<style>a > b { x }</style>", id="rawtext-style"),
        pytest.param("<script>1 < 2 && 3</script>", "script", "<script>1 < 2 && 3</script>", id="rawtext-script"),
        pytest.param("<xmp><b></xmp>", "xmp", "<xmp><b></xmp>", id="rawtext-xmp"),
        pytest.param("<plaintext>a & <b>", "plaintext", "<plaintext>a & <b></plaintext>", id="rawtext-plaintext"),
        pytest.param(
            "<body><noscript>a&lt;b</noscript>", "noscript", "<noscript>a&lt;b</noscript>", id="noscript-escaped"
        ),
        pytest.param("<svg><circle r=5></circle></svg>", "svg", '<svg><circle r="5"></circle></svg>', id="foreign-svg"),
        pytest.param("<svg><title>a&b</title></svg>", "svg", "<svg><title>a&amp;b</title></svg>", id="foreign-text"),
    ],
)
def test_html_serialization(find: Callable[[str, str], Element], html: str, selector: str, expected: str) -> None:
    assert find(html, selector).html == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("a&lt;b&gt;c", "a&lt;b&gt;c", id="angle-brackets"),
        pytest.param("a&amp;b", "a&amp;b", id="ampersand"),
        pytest.param("a&nbsp;b", "a&nbsp;b", id="nbsp"),
    ],
)
def test_text_is_escaped_in_html(find: Callable[[str, str], Element], source: str, expected: str) -> None:
    assert find(f"<p>{source}</p>", "p").html == f"<p>{expected}</p>"


@pytest.mark.parametrize(
    ("markup", "expected_value"),
    [
        pytest.param('"a&b"', "&amp;", id="amp-in-value"),
        pytest.param('"a\u00a0b"', "&nbsp;", id="nbsp-in-value"),
        pytest.param("'say \"hi\"'", "&quot;", id="quote-in-value"),
    ],
)
def test_attribute_values_are_escaped(find: Callable[[str, str], Element], markup: str, expected_value: str) -> None:
    assert expected_value in find(f"<p title={markup}>x</p>", "p").html


@pytest.mark.parametrize(
    ("attr", "value"),
    [
        pytest.param("checked", "", id="valueless"),
        pytest.param("type", "text", id="valued"),
    ],
)
def test_attrs_mapping(find: Callable[[str, str], Element], attr: str, value: str) -> None:
    markup = f"{attr}={value}" if value else attr
    assert find(f"<input {markup}>", "input").attrs[attr] == value


@pytest.mark.parametrize(
    ("context", "selector", "expected"),
    [
        pytest.param("<div>", "div", Namespace.HTML, id="html"),
        pytest.param("<svg><circle></svg>", "circle", Namespace.SVG, id="svg"),
        pytest.param("<math><mi>x</mi></math>", "mi", Namespace.MATHML, id="mathml"),
    ],
)
def test_namespace(find: Callable[[str, str], Element], context: str, selector: str, expected: Namespace) -> None:
    assert find(f"<body>{context}</body>", selector).namespace is expected


@pytest.mark.parametrize(
    ("html", "node_type", "expected"),  # expected = (data, text, serialized)
    [
        pytest.param("<p>hello</p>", Text, ("hello", "hello", "hello"), id="text"),
        pytest.param("<!--c-->", Comment, ("c", "", "<!--c-->"), id="comment"),
        pytest.param("<!---->", Comment, ("", "", "<!---->"), id="empty-comment"),
    ],
)
def test_leaf_node_accessors(
    first: Callable[[str, type[Node]], Node], html: str, node_type: type[Node], expected: tuple[str, str, str]
) -> None:
    data, text, serialized = expected
    node = first(html, node_type)
    assert node.data == data  # ty: ignore[unresolved-attribute]  # Text and Comment both expose .data
    assert node.text == text  # .text counts Text descendants only, so a comment contributes nothing
    assert node.html == serialized


@pytest.mark.parametrize(
    ("doctype", "name"),
    [
        pytest.param("<!DOCTYPE html>", "html", id="bare"),
        pytest.param('<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN">', "html", id="with-public-id"),
    ],
)
def test_doctype_name(first: Callable[[str, type[Node]], Node], doctype: str, name: str) -> None:
    node = first(doctype, Doctype)
    assert node.name == name  # ty: ignore[unresolved-attribute]  # node is a Doctype here
    assert node.html == f"<!DOCTYPE {name}>"


def test_document_html_round_trips() -> None:
    source = "<!DOCTYPE html><html><head></head><body><p>hi</p></body></html>"
    assert parse(source).html == source


def test_document_text_skips_comments_and_doctype() -> None:
    doc = parse("<!-- c --><!DOCTYPE html><html><body>hello</body></html>")
    assert doc.text == "hello"


def test_template_content_serializes_and_collects_text(find: Callable[[str, str], Element]) -> None:
    template = find("<template>inner</template>", "template")
    assert template.html == "<template>inner</template>"
    assert template.text == "inner"
