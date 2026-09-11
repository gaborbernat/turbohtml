"""The serialize()/encode() output options: sort_attributes and meta_charset."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from turbohtml import Canonical, Element, Html, Indent, Markdown, Minify, PlainText, parse


@pytest.mark.parametrize(
    ("markup", "selector", "expected"),
    [
        pytest.param("<p z=1 a=2 m=3>x", "p", '<p a="2" m="3" z="1">x</p>', id="three-attrs"),
        pytest.param("<p a=1>x", "p", '<p a="1">x</p>', id="single-attr-unchanged"),
        pytest.param("<p>x", "p", "<p>x</p>", id="no-attrs-unchanged"),
        pytest.param("<input name=q value=1>", "input", '<input name="q" value="1">', id="void-element"),
    ],
)
def test_sort_attributes_orders_by_name(markup: str, selector: str, expected: str) -> None:
    node = parse(markup).select_one(selector)
    assert node is not None
    assert node.serialize(Html(sort_attributes=True)) == expected


def test_sort_attributes_off_keeps_source_order() -> None:
    node = parse("<p z=1 a=2>x").select_one("p")
    assert node is not None
    assert node.serialize() == '<p z="1" a="2">x</p>'


@pytest.mark.parametrize(
    ("attrs", "expected"),
    [
        pytest.param({"ab": "1", "a": "2"}, '<x a="2" ab="1"></x>', id="prefix-name-after-longer"),
        pytest.param({"a": "1", "ab": "2"}, '<x a="1" ab="2"></x>', id="prefix-name-before-longer"),
    ],
)
def test_sort_attributes_orders_prefix_names(attrs: dict[str, str], expected: str) -> None:
    assert Element("x", attrs).serialize(Html(sort_attributes=True)) == expected


def test_sort_attributes_beyond_stack_buffer_uses_heap() -> None:
    names = [f"a{index:02d}" for index in range(70)]
    element = Element("x", dict.fromkeys(reversed(names), ""))
    expected = "<x " + " ".join(f'{name}=""' for name in names) + "></x>"
    assert element.serialize(Html(sort_attributes=True)) == expected


def test_sort_attributes_composes_with_indent() -> None:
    node = parse("<p z=1 a=2>x").select_one("p")
    assert node is not None
    assert node.serialize(Html(layout=Indent(2), sort_attributes=True)).splitlines()[0] == '<p a="2" z="1">'


def test_sort_attributes_composes_with_minify() -> None:
    node = parse("<p z=1 a=2>x").select_one("p")
    assert node is not None
    assert node.serialize(Html(layout=Minify(), sort_attributes=True)) == "<p a=2 z=1>x</p>"


def test_meta_charset_injects_into_empty_head() -> None:
    out = parse("<p>x").serialize(Html(meta_charset=True))
    assert out == '<html><head><meta charset="utf-8"></head><body><p>x</p></body></html>'


def test_meta_charset_injects_before_existing_head_content() -> None:
    out = parse("<link rel=icon>").serialize(Html(meta_charset=True))
    assert out == '<html><head><meta charset="utf-8"><link rel="icon"></head><body></body></html>'


def test_meta_charset_normalizes_existing_charset_meta() -> None:
    out = parse("<meta charset=ascii>").serialize(Html(meta_charset=True))
    assert out == '<html><head><meta charset="utf-8"></head><body></body></html>'


def test_meta_charset_keeps_other_attributes_on_charset_meta() -> None:
    out = parse("<meta charset=ascii id=enc>").serialize(Html(meta_charset=True))
    assert out == '<html><head><meta charset="utf-8" id="enc"></head><body></body></html>'


def test_meta_charset_normalizes_http_equiv_content_type() -> None:
    out = parse('<meta http-equiv=content-type content="text/html; charset=ascii">').serialize(Html(meta_charset=True))
    expected = '<html><head><meta http-equiv="content-type" content="text/html; charset=utf-8">'
    assert out.startswith(expected)
    assert out.count("charset=") == 1


def test_meta_charset_matches_mixed_case_http_equiv_value() -> None:
    out = parse('<meta http-equiv="Content-Type" content="text/html; charset=ascii">').serialize(
        Html(meta_charset=True)
    )
    expected = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
    assert out.startswith(expected)
    assert out.count("charset=") == 1


def test_meta_charset_ignores_unrelated_http_equiv() -> None:
    out = parse('<meta http-equiv=refresh content="5">').serialize(Html(meta_charset=True))
    assert out.startswith('<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="5">')


def test_meta_charset_ignores_http_equiv_content_type_without_content() -> None:
    out = parse("<meta http-equiv=content-type>").serialize(Html(meta_charset=True))
    assert out.startswith('<html><head><meta charset="utf-8"><meta http-equiv="content-type">')


@pytest.mark.parametrize(
    "equiv",
    [
        pytest.param("content", id="shorter-prefix"),
        pytest.param("content-type-x", id="longer-than-label"),
    ],
)
def test_meta_charset_http_equiv_label_mismatch_injects(equiv: str) -> None:
    out = parse(f'<meta http-equiv="{equiv}" content="x">').serialize(Html(meta_charset=True))
    assert out.startswith('<html><head><meta charset="utf-8">')


def test_meta_charset_ignores_meta_without_charset_or_http_equiv() -> None:
    out = parse('<meta name=viewport content="width=1">').serialize(Html(meta_charset=True))
    assert out.startswith('<html><head><meta charset="utf-8"><meta name="viewport" content="width=1">')


def test_meta_charset_keeps_seven_char_attr_on_charset_meta() -> None:
    out = parse('<meta charset=ascii content="x">').serialize(Html(meta_charset=True))
    assert out.startswith('<html><head><meta charset="utf-8" content="x">')


def test_meta_charset_keeps_seven_char_attr_on_content_type_meta() -> None:
    out = parse('<meta http-equiv=content-type content="text/html" enabled="x">').serialize(Html(meta_charset=True))
    assert out.startswith('<html><head><meta http-equiv="content-type" content="text/html; charset=utf-8" enabled="x">')


def test_meta_charset_with_indent_leaves_foreign_element() -> None:
    out = parse("<svg></svg>").serialize(Html(layout=Indent(2), meta_charset=True))
    assert '<meta charset="utf-8">' in out
    assert "<svg></svg>" in out


def test_meta_charset_skips_non_element_head_children() -> None:
    out = parse("<head><!--note--><title>t").serialize(Html(meta_charset=True))
    assert out == ('<html><head><meta charset="utf-8"><!--note--><title>t</title></head><body></body></html>')


def test_meta_charset_off_injects_nothing() -> None:
    assert parse("<p>x").serialize() == "<html><head></head><body><p>x</p></body></html>"


def test_meta_charset_no_head_is_a_no_op() -> None:
    node = parse("<p id=a>x").select_one("p")
    assert node is not None
    assert node.serialize(Html(meta_charset=True)) == '<p id="a">x</p>'


def test_meta_charset_leaves_foreign_elements_untouched() -> None:
    node = parse("<svg><circle r=5></circle></svg>").select_one("svg")
    assert node is not None
    assert node.serialize(Html(meta_charset=True)) == '<svg><circle r="5"></circle></svg>'


def test_meta_charset_reparses_to_one_declaration() -> None:
    out = parse("<title>t").serialize(Html(meta_charset=True))
    metas = parse(out).select("meta")
    assert len(metas) == 1
    assert metas[0].attrs["charset"] == "utf-8"


def test_meta_charset_with_indent_indents_injected_meta() -> None:
    out = parse("<p>x").serialize(Html(layout=Indent(2), meta_charset=True))
    assert out == (
        "<html>\n"
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        "  </head>\n"
        "  <body>\n"
        "    <p>\n"
        "      x\n"
        "    </p>\n"
        "  </body>\n"
        "</html>"
    )


def test_meta_charset_with_indent_non_empty_head() -> None:
    out = parse("<link rel=icon>").serialize(Html(layout=Indent(2), meta_charset=True))
    assert out == (
        '<html>\n  <head>\n    <meta charset="utf-8">\n    <link rel="icon">\n  </head>\n  <body></body>\n</html>'
    )


def test_meta_charset_with_indent_normalizes_existing_meta() -> None:
    out = parse("<meta charset=ascii>").serialize(Html(layout=Indent(2), meta_charset=True))
    assert out == ('<html>\n  <head>\n    <meta charset="utf-8">\n  </head>\n  <body></body>\n</html>')


def test_meta_charset_with_minify_injects() -> None:
    out = parse("<title>t").serialize(Html(layout=Minify(), meta_charset=True))
    assert out.startswith('<meta charset="utf-8">')
    metas = parse(out).select("meta")
    assert len(metas) == 1
    assert metas[0].attrs["charset"] == "utf-8"


def test_meta_charset_with_minify_normalizes_existing_meta() -> None:
    out = parse("<meta charset=ascii><title>t").serialize(Html(layout=Minify(), meta_charset=True))
    metas = parse(out).select("meta")
    assert len(metas) == 1
    assert metas[0].attrs["charset"] == "utf-8"
    assert 'charset="utf-8"' in out


def test_encode_meta_charset_uses_target_encoding() -> None:
    out = parse("<p>x").encode("iso-8859-1", Html(meta_charset=True))
    assert out == ('<html><head><meta charset="iso-8859-1"></head><body><p>x</p></body></html>'.encode("latin-1"))


def test_encode_sort_attributes() -> None:
    node = parse("<p z=1 a=2>x").select_one("p")
    assert node is not None
    assert node.encode(options=Html(sort_attributes=True)) == b'<p a="2" z="1">x</p>'


def test_serialize_rejects_another_renderers_config() -> None:
    with pytest.raises(TypeError, match="options must be a Html, not Markdown"):
        parse("<p>x</p>").serialize(Markdown())  # ty: ignore[invalid-argument-type]  # the wrong config class is rejected


@dataclass(frozen=True)
class _SortedHtml(Html):
    sort_attributes: bool = True


@dataclass(frozen=True)
class _ImageText(PlainText):
    images: bool = True


@dataclass(frozen=True)
class _CommentedCanonical(Canonical):
    with_comments: bool = True


@dataclass(frozen=True)
class _ExtendedHtml(_SortedHtml):
    extra: str = "value"


@dataclass(frozen=True)
class _ExtendedText(_ImageText):
    extra: str = "value"


@dataclass(frozen=True)
class _ExtendedCanonical(_CommentedCanonical):
    extra: str = "value"


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        pytest.param(Html(), '<p z="1" a="2"><img alt="picture"><!--note--></p>', id="html-default"),
        pytest.param(_SortedHtml(), '<p a="2" z="1"><img alt="picture"><!--note--></p>', id="html-subclass"),
        pytest.param(PlainText(), "", id="text-default"),
        pytest.param(_ImageText(), "picture", id="text-subclass"),
        pytest.param(Canonical(), b'<p a="2" z="1"><img alt="picture"></img></p>', id="canonical-default"),
        pytest.param(
            _CommentedCanonical(),
            b'<p a="2" z="1"><img alt="picture"></img><!--note--></p>',
            id="canonical-subclass",
        ),
    ],
)
def test_render_options_preserve_subclass_defaults(
    options: Html | PlainText | Canonical, expected: str | bytes
) -> None:
    assert _render(options) == expected


@pytest.mark.parametrize(
    "options",
    [
        pytest.param(_ExtendedHtml(), id="html"),
        pytest.param(_ExtendedText(), id="text"),
        pytest.param(_ExtendedCanonical(), id="canonical"),
    ],
)
def test_render_options_reject_subclass_extra_fields(options: Html | PlainText | Canonical) -> None:
    with pytest.raises(AttributeError, match="has no attribute 'extra'"):
        _render(options)


def _render(options: Html | PlainText | Canonical) -> str | bytes:
    document: Final = parse('<p z="1" a="2"><img alt="picture"><!--note--></p>').select("p")[0]
    if isinstance(options, Html):
        return document.serialize(options)
    if isinstance(options, PlainText):
        return document.to_text(options)
    return document.canonicalize(options)
