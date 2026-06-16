"""The controllable serializer: inner_html, Formatter variants, indent, encode."""

from __future__ import annotations

import pytest

from turbohtml import Formatter, Node, parse


def _one(html: str, selector: str) -> Node:
    node = parse(html).select_one(selector)
    assert node is not None
    return node


# --- inner_html ---


def test_inner_html_is_children_only() -> None:
    div = _one("<div><p>hi</p><span>x</span></div>", "div")
    assert div.inner_html == "<p>hi</p><span>x</span>"
    assert div.html == "<div><p>hi</p><span>x</span></div>"


def test_inner_html_of_a_leaf_is_empty() -> None:
    assert _one("<p>x</p>", "p").inner_html == "x"  # the text child
    assert not _one("<br>", "br").inner_html  # a void element has no children


# --- escaping under the default WHATWG formatter ---


def test_whatwg_attribute_leaves_angles_literal() -> None:
    a = _one('<a title="a&amp;b&lt;c&gt;d&quot;e&nbsp;f">t</a>', "a")
    # attribute context escapes & " nbsp and leaves < > literal, per the spec
    assert a.html == '<a title="a&amp;b<c>d&quot;e&nbsp;f">t</a>'


def test_whatwg_text_keeps_a_literal_quote() -> None:
    # text context does not escape the double quote (only attribute values do)
    assert _one("<p>say &quot;hi&quot;</p>", "p").inner_html == 'say "hi"'


# --- the pre/textarea/listing leading-newline rule ---


def test_pre_re_emits_a_significant_leading_newline() -> None:
    # the parser drops one newline after <pre>; serialization restores it so a
    # two-newline source round-trips
    assert _one("<pre>\n\nkeep</pre>", "pre").html == "<pre>\n\nkeep</pre>"
    assert _one("<textarea>\n\nx</textarea>", "textarea").html == "<textarea>\n\nx</textarea>"
    assert _one("<listing>\n\ny</listing>", "listing").html == "<listing>\n\ny</listing>"


def test_pre_without_a_leading_newline_is_unchanged() -> None:
    assert _one("<pre>plain</pre>", "pre").html == "<pre>plain</pre>"


def test_pre_with_a_non_text_first_child_adds_no_newline() -> None:
    assert _one("<pre><span>x</span></pre>", "pre").html == "<pre><span>x</span></pre>"


def test_empty_pre_adds_no_newline() -> None:
    assert _one("<pre></pre>", "pre").html == "<pre></pre>"


# --- Formatter variants ---


def test_minimal_escapes_only_structural_characters() -> None:
    p = _one("<p>a&amp;b&lt;c&gt;d&nbsp;e</p>", "p")
    assert p.serialize(formatter=Formatter.MINIMAL) == "<p>a&amp;b&lt;c&gt;d\xa0e</p>"
    a = _one('<a title="a&lt;b&quot;c&nbsp;d">t</a>', "a")
    # minimal escapes < in attributes too and leaves " and nbsp literal
    assert a.serialize(formatter=Formatter.MINIMAL) == '<a title="a&lt;b"c\xa0d">t</a>'


def test_named_entities_uses_html_names() -> None:
    p = _one("<p>café &amp; résumé&nbsp;x</p>", "p")
    assert p.inner_html == "café &amp; résumé&nbsp;x"  # the default keeps non-ASCII literal
    assert p.serialize(formatter=Formatter.NAMED_ENTITIES) == "<p>caf&eacute; &amp; r&eacute;sum&eacute;&nbsp;x</p>"


def test_named_entities_keeps_characters_without_a_name() -> None:
    assert _one("<p>ab12</p>", "p").serialize(formatter=Formatter.NAMED_ENTITIES) == "<p>ab12</p>"


def test_named_entities_escapes_structural_ascii() -> None:
    p = _one("<p>a&lt;b&gt;c&quot;d&amp;e</p>", "p")
    assert p.serialize(formatter=Formatter.NAMED_ENTITIES) == "<p>a&lt;b&gt;c&quot;d&amp;e</p>"


def test_named_entities_passes_through_unnamed_non_ascii() -> None:
    # a C1 control below the table and an astral emoji above it have no named
    # reference, so they stay literal (and exercise both ends of the table search)
    p = _one("<p>\x85\U0001f600</p>", "p")
    assert p.serialize(formatter=Formatter.NAMED_ENTITIES) == "<p>\x85\U0001f600</p>"


# --- pretty printing via indent ---


def test_indent_int_pretty_prints() -> None:
    ul = _one("<ul><li>a</li><li>b</li></ul>", "ul")
    assert ul.serialize(indent=2) == "<ul>\n  <li>\n    a\n  </li>\n  <li>\n    b\n  </li>\n</ul>"


def test_indent_str_uses_the_unit_verbatim() -> None:
    div = _one("<div><p>x</p></div>", "div")
    assert div.serialize(indent="\t") == "<div>\n\t<p>\n\t\tx\n\t</p>\n</div>"


def test_indent_zero_adds_newlines_without_indentation() -> None:
    div = _one("<div><p>x</p></div>", "div")
    assert div.serialize(indent=0) == "<div>\n<p>\nx\n</p>\n</div>"


def test_pretty_empty_element_stays_on_one_line() -> None:
    assert _one("<div></div>", "div").serialize(indent=2) == "<div></div>"


def test_pretty_void_element() -> None:
    assert _one("<p><br></p>", "p").serialize(indent=2) == "<p>\n  <br>\n</p>"


def test_pretty_preserves_raw_and_pre_content() -> None:
    assert _one("<div><pre>\n\nkeep</pre></div>", "div").serialize(indent=2) == "<div>\n  <pre>\n\nkeep</pre>\n</div>"
    assert _one("<div><script>a<b</script></div>", "div").serialize(indent=2) == "<div>\n  <script>a<b</script>\n</div>"


def test_pretty_document_includes_doctype_and_comment() -> None:
    # a comment before the root and the doctype are document-level nodes at depth 0
    pretty = parse("<!DOCTYPE html><!--c--><title>t").serialize(indent=2)
    assert pretty.startswith("<!DOCTYPE html>\n<!--c-->\n<html>\n  <head>")


def test_pretty_template_content() -> None:
    template = _one("<template><p>x</p></template>", "template")
    assert template.serialize(indent=2) == "<template>\n  <p>\n    x\n  </p>\n</template>"


def test_pretty_foreign_element() -> None:
    # a foreign element is laid out like any non-void element, not preserved
    svg = _one("<svg><circle r=1></circle></svg>", "svg")
    assert svg.serialize(indent=2) == '<svg>\n  <circle r="1"></circle>\n</svg>'


def test_pretty_preserves_textarea_and_listing() -> None:
    # plain content (no leading newline) so the element-name test, not the
    # leading-newline rule, drives the decision to preserve
    assert _one("<div><pre>plain</pre></div>", "div").serialize(indent=2) == "<div>\n  <pre>plain</pre>\n</div>"
    assert _one("<div><textarea>x</textarea></div>", "div").serialize(indent=2) == (
        "<div>\n  <textarea>x</textarea>\n</div>"
    )
    assert _one("<div><listing>a b</listing></div>", "div").serialize(indent=2) == (
        "<div>\n  <listing>a b</listing>\n</div>"
    )


def test_serialize_indent_none_is_compact() -> None:
    div = _one("<div><p>x</p></div>", "div")
    assert div.serialize(indent=None) == "<div><p>x</p></div>"


def test_default_serialize_matches_html() -> None:
    div = _one("<div><p>hi</p></div>", "div")
    assert div.serialize() == div.html  # WHATWG, compact


# --- encode ---


def test_encode_defaults_to_utf8() -> None:
    assert _one("<p>café</p>", "p").encode() == "<p>café</p>".encode()


def test_encode_to_ascii_with_named_entities() -> None:
    assert _one("<p>café</p>", "p").encode("ascii", formatter=Formatter.NAMED_ENTITIES) == b"<p>caf&eacute;</p>"


def test_encode_honours_indent() -> None:
    div = _one("<div><p>x</p></div>", "div")
    assert div.encode(indent=2) == b"<div>\n  <p>\n    x\n  </p>\n</div>"


def test_encode_rejects_an_unknown_encoding() -> None:
    with pytest.raises(LookupError):
        _one("<p>x</p>", "p").encode("not-a-codec")


def test_encode_raises_on_unencodable_characters() -> None:
    # the default WHATWG formatter keeps é literal, so ascii cannot represent it
    with pytest.raises(UnicodeEncodeError):
        _one("<p>café</p>", "p").encode("ascii")


# --- argument validation ---


def test_serialize_rejects_a_non_formatter() -> None:
    with pytest.raises(TypeError, match="Formatter"):
        _one("<p>x</p>", "p").serialize(formatter="whatwg")  # ty: ignore[invalid-argument-type]  # a str, not the enum


def test_serialize_rejects_a_bad_indent_type() -> None:
    with pytest.raises(TypeError, match="indent"):
        _one("<p>x</p>", "p").serialize(indent=1.5)  # ty: ignore[invalid-argument-type]  # float is not int/str/None


def test_serialize_rejects_a_negative_indent() -> None:
    with pytest.raises(ValueError, match="negative"):
        _one("<p>x</p>", "p").serialize(indent=-1)


def test_serialize_rejects_positional_arguments() -> None:
    with pytest.raises(TypeError):
        _one("<p>x</p>", "p").serialize("whatwg")  # ty: ignore[too-many-positional-arguments]  # keyword-only


def test_encode_rejects_extra_positional_arguments() -> None:
    with pytest.raises(TypeError):
        _one("<p>x</p>", "p").encode("utf-8", "extra")  # ty: ignore[too-many-positional-arguments]


def test_encode_propagates_a_formatter_error() -> None:
    with pytest.raises(TypeError, match="Formatter"):
        _one("<p>x</p>", "p").encode(formatter="whatwg")  # ty: ignore[invalid-argument-type]  # not the enum


# --- the Formatter enum ---


def test_formatter_members() -> None:
    assert Formatter.WHATWG.value == "whatwg"
    assert Formatter.MINIMAL.value == "minimal"
    assert Formatter.NAMED_ENTITIES.value == "named"
