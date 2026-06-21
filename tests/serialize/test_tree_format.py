"""The controllable serializer: inner_html, Formatter variants, indent, encode."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import Formatter, Indent, Node, parse

if TYPE_CHECKING:
    from collections.abc import Callable


def _one(html: str, selector: str) -> Node:
    node = parse(html).select_one(selector)
    assert node is not None
    return node


@pytest.mark.parametrize(
    ("html", "selector", "inner", "outer"),
    [
        pytest.param(
            "<div><p>hi</p><span>x</span></div>",
            "div",
            "<p>hi</p><span>x</span>",
            "<div><p>hi</p><span>x</span></div>",
            id="children-only",
        ),
        pytest.param("<p>x</p>", "p", "x", "<p>x</p>", id="leaf-text-child"),
        pytest.param("<br>", "br", "", "<br>", id="void-has-no-children"),
    ],
)
def test_inner_html(html: str, selector: str, inner: str, outer: str) -> None:
    node = _one(html, selector)
    assert node.inner_html == inner
    assert node.html == outer


def test_whatwg_attribute_leaves_angles_literal() -> None:
    anchor = _one('<a title="a&amp;b&lt;c&gt;d&quot;e&nbsp;f">t</a>', "a")
    assert anchor.html == '<a title="a&amp;b<c>d&quot;e&nbsp;f">t</a>'


def test_whatwg_text_keeps_a_literal_quote() -> None:
    assert _one("<p>say &quot;hi&quot;</p>", "p").inner_html == 'say "hi"'


def test_default_formatter_keeps_non_ascii_literal() -> None:
    assert _one("<p>café &amp; résumé&nbsp;x</p>", "p").inner_html == "café &amp; résumé&nbsp;x"


@pytest.mark.parametrize(
    ("html", "selector", "formatter", "expected"),
    [
        pytest.param(
            "<p>a&amp;b&lt;c&gt;d&nbsp;e</p>",
            "p",
            Formatter.MINIMAL,
            "<p>a&amp;b&lt;c&gt;d\xa0e</p>",
            id="minimal-text",
        ),
        pytest.param(
            '<a title="a&lt;b&quot;c&nbsp;d">t</a>',
            "a",
            Formatter.MINIMAL,
            '<a title="a&lt;b"c\xa0d">t</a>',
            id="minimal-attribute",
        ),
        pytest.param(
            "<p>café &amp; résumé&nbsp;x</p>",
            "p",
            Formatter.NAMED_ENTITIES,
            "<p>caf&eacute; &amp; r&eacute;sum&eacute;&nbsp;x</p>",
            id="named-uses-html-names",
        ),
        pytest.param("<p>ab12</p>", "p", Formatter.NAMED_ENTITIES, "<p>ab12</p>", id="named-keeps-unnamed"),
        pytest.param(
            "<p>a&lt;b&gt;c&quot;d&amp;e</p>",
            "p",
            Formatter.NAMED_ENTITIES,
            "<p>a&lt;b&gt;c&quot;d&amp;e</p>",
            id="named-escapes-structural-ascii",
        ),
        # a C1 control below the table and an astral emoji above it have no named
        # reference, so they stay literal (exercising both ends of the table search)
        pytest.param(
            "<p>\x85\U0001f600</p>",
            "p",
            Formatter.NAMED_ENTITIES,
            "<p>\x85\U0001f600</p>",
            id="named-passes-unnamed-non-ascii",
        ),
    ],
)
def test_formatter_serialize(html: str, selector: str, formatter: Formatter, expected: str) -> None:
    assert _one(html, selector).serialize(formatter=formatter) == expected


@pytest.mark.parametrize(
    ("html", "selector", "indent", "expected"),
    [
        pytest.param(
            "<ul><li>a</li><li>b</li></ul>",
            "ul",
            2,
            "<ul>\n  <li>\n    a\n  </li>\n  <li>\n    b\n  </li>\n</ul>",
            id="int-pretty-prints",
        ),
        pytest.param("<div><p>x</p></div>", "div", "\t", "<div>\n\t<p>\n\t\tx\n\t</p>\n</div>", id="str-unit-verbatim"),
        pytest.param("<div><p>x</p></div>", "div", 0, "<div>\n<p>\nx\n</p>\n</div>", id="zero-newlines-no-indent"),
        pytest.param("<div></div>", "div", 2, "<div></div>", id="empty-element-one-line"),
        pytest.param("<p><br></p>", "p", 2, "<p>\n  <br>\n</p>", id="void-element"),
        pytest.param("<frameset><frame>", "frameset", 2, "<frameset>\n  <frame>\n</frameset>", id="void-frame"),
        pytest.param("<div><pre>\n\nkeep</pre></div>", "div", 2, "<div>\n  <pre>\n\nkeep</pre>\n</div>", id="raw-pre"),
        pytest.param(
            "<div><script>a<b</script></div>", "div", 2, "<div>\n  <script>a<b</script>\n</div>", id="raw-script"
        ),
        pytest.param(
            "<template><p>x</p></template>",
            "template",
            2,
            "<template>\n  <p>\n    x\n  </p>\n</template>",
            id="template-content",
        ),
        # a foreign element is laid out like any non-void element, not preserved
        pytest.param(
            "<svg><circle r=1></circle></svg>", "svg", 2, '<svg>\n  <circle r="1"></circle>\n</svg>', id="foreign"
        ),
        # plain content (no leading newline) so the element-name test, not the
        # leading-newline rule, drives the decision to preserve
        pytest.param("<div><pre>plain</pre></div>", "div", 2, "<div>\n  <pre>plain</pre>\n</div>", id="preserve-pre"),
        pytest.param(
            "<div><textarea>x</textarea></div>",
            "div",
            2,
            "<div>\n  <textarea>x</textarea>\n</div>",
            id="preserve-textarea",
        ),
        pytest.param(
            "<div><listing>a b</listing></div>",
            "div",
            2,
            "<div>\n  <listing>a b</listing>\n</div>",
            id="preserve-listing",
        ),
        pytest.param("<div><p>x</p></div>", "div", None, "<div><p>x</p></div>", id="none-is-compact"),
    ],
)
def test_serialize_indent(html: str, selector: str, indent: int | str | None, expected: str) -> None:
    layout = None if indent is None else Indent(indent)
    assert _one(html, selector).serialize(layout=layout) == expected


# the parser drops one newline after <pre>; serialization restores it so a
# two-newline source round-trips, while plain content is left unchanged
@pytest.mark.parametrize(
    ("html", "selector", "expected"),
    [
        pytest.param("<pre>\n\nkeep</pre>", "pre", "<pre>\n\nkeep</pre>", id="pre-double-newline"),
        pytest.param(
            "<textarea>\n\nx</textarea>", "textarea", "<textarea>\n\nx</textarea>", id="textarea-double-newline"
        ),
        pytest.param("<listing>\n\ny</listing>", "listing", "<listing>\n\ny</listing>", id="listing-double-newline"),
        pytest.param("<pre>plain</pre>", "pre", "<pre>plain</pre>", id="no-leading-newline"),
        pytest.param("<pre><span>x</span></pre>", "pre", "<pre><span>x</span></pre>", id="non-text-first-child"),
        pytest.param("<pre></pre>", "pre", "<pre></pre>", id="empty"),
    ],
)
def test_pre_leading_newline_rule(html: str, selector: str, expected: str) -> None:
    assert _one(html, selector).html == expected


def test_pretty_document_includes_doctype_and_comment() -> None:
    pretty = parse("<!DOCTYPE html><!--c--><title>t").serialize(layout=Indent(2))
    assert pretty.startswith("<!DOCTYPE html>\n<!--c-->\n<html>\n  <head>")


def test_default_serialize_matches_html() -> None:
    div = _one("<div><p>hi</p></div>", "div")
    assert div.serialize() == div.html  # WHATWG, compact


def test_indent_defaults_to_two_spaces() -> None:
    assert Indent().unit == "  "


def test_indent_int_and_str_units() -> None:
    assert Indent(4).unit == "    "
    assert Indent("\t").unit == "\t"
    assert not Indent(0).unit


def test_indent_repr() -> None:
    assert repr(Indent(2)) == "Indent('  ')"


def test_indent_equality_and_hash() -> None:
    assert Indent(2) == Indent("  ")
    assert Indent(2) != Indent(4)
    assert Indent(2) != "Indent(2)"
    assert (Indent(2) == 3) is False
    assert hash(Indent(2)) == hash(Indent("  "))


def test_indent_unorderable() -> None:
    with pytest.raises(TypeError):
        _ = Indent(2) < Indent(4)  # ty: ignore[unsupported-operator]  # ordering is unsupported on purpose


def test_indent_not_equal_same_length() -> None:
    # same unit length, different content: forces the value comparison, not the length shortcut
    assert Indent(" ") != Indent("\t")


def test_indent_rejects_extra_positional() -> None:
    with pytest.raises(TypeError):
        Indent(2, 4)  # ty: ignore[too-many-positional-arguments]  # takes one argument


@pytest.mark.parametrize(
    ("html", "selector", "kwargs", "expected"),
    [
        pytest.param("<p>café</p>", "p", {}, "<p>café</p>".encode(), id="defaults-to-utf8"),
        pytest.param(
            "<p>café</p>",
            "p",
            {"encoding": "ascii", "formatter": Formatter.NAMED_ENTITIES},
            b"<p>caf&eacute;</p>",
            id="ascii-with-named-entities",
        ),
        pytest.param(
            "<div><p>x</p></div>",
            "div",
            {"layout": Indent(2)},
            b"<div>\n  <p>\n    x\n  </p>\n</div>",
            id="honours-indent",
        ),
    ],
)
def test_encode(html: str, selector: str, kwargs: dict[str, object], expected: bytes) -> None:
    assert _one(html, selector).encode(**kwargs) == expected  # ty: ignore[invalid-argument-type]  # object-typed kwargs


@pytest.mark.parametrize(
    ("html", "kwargs", "exception"),
    [
        pytest.param("<p>x</p>", {"encoding": "not-a-codec"}, LookupError, id="unknown-encoding"),
        # the default WHATWG formatter keeps é literal, so ascii cannot represent it
        pytest.param("<p>café</p>", {"encoding": "ascii"}, UnicodeEncodeError, id="unencodable-character"),
    ],
)
def test_encode_raises(html: str, kwargs: dict[str, object], exception: type[Exception]) -> None:
    with pytest.raises(exception):
        _one(html, "p").encode(**kwargs)  # ty: ignore[invalid-argument-type]  # object-typed kwargs


@pytest.mark.parametrize(
    ("call", "exception", "match"),
    [
        pytest.param(
            lambda node: node.serialize(formatter="whatwg"), TypeError, "Formatter", id="serialize-non-formatter"
        ),
        pytest.param(
            lambda node: node.serialize(layout=Indent(1.5)),  # ty: ignore[invalid-argument-type]  # non-int/str on purpose
            TypeError,
            "indent",
            id="indent-bad-type",
        ),
        pytest.param(lambda node: node.serialize(layout=Indent(-1)), ValueError, "negative", id="indent-negative"),
        pytest.param(lambda node: node.serialize(layout="whatwg"), TypeError, "layout", id="serialize-bad-layout"),
        pytest.param(lambda node: node.serialize("whatwg"), TypeError, None, id="serialize-positional"),
        pytest.param(lambda node: node.encode("utf-8", "extra"), TypeError, None, id="encode-extra-positional"),
        pytest.param(lambda node: node.encode(formatter="whatwg"), TypeError, "Formatter", id="encode-non-formatter"),
    ],
)
def test_serialize_encode_argument_validation(
    call: Callable[[Node], object], exception: type[Exception], match: str | None
) -> None:
    with pytest.raises(exception, match=match):
        call(_one("<p>x</p>", "p"))


@pytest.mark.parametrize(
    ("member", "value"),
    [
        pytest.param(Formatter.WHATWG, "whatwg", id="whatwg"),
        pytest.param(Formatter.MINIMAL, "minimal", id="minimal"),
        pytest.param(Formatter.NAMED_ENTITIES, "named", id="named"),
    ],
)
def test_formatter_members(member: Formatter, value: str) -> None:
    assert member.value == value
