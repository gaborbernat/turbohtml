"""The to_markdown(google_doc=True) mode: turning the inline-CSS styling a Google
Docs export carries into Markdown, the html2text google_doc surface.

One golden case per behavior, plus the binding's validation, so every CSS code
path in the C walker is exercised.
"""

from __future__ import annotations

import pytest

from turbohtml import Markdown, parse


def md(html: str, config: Markdown) -> str:
    return parse(html).to_markdown(config)


@pytest.mark.parametrize(
    ("html", "config", "expected"),
    [
        pytest.param(
            '<p><span style="font-weight:700">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**a**",
            id="font-weight-700-is-bold",
        ),
        pytest.param(
            '<p><span style="font-weight:bold">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**a**",
            id="font-weight-bold-keyword",
        ),
        pytest.param(
            '<p><span style="font-weight:800">a</span><span style="font-weight:900">b</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**a****b**",
            id="font-weight-800-and-900",
        ),
        pytest.param(
            '<p><span style="font-weight:400">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "a",
            id="font-weight-400-is-not-bold",
        ),
        pytest.param(
            '<p><span style="font-weight:bolder">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "a",
            id="value-longer-than-keyword-not-bold",
        ),
        pytest.param(
            '<p><span style="font-weight:70">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "a",
            id="value-shorter-than-keyword-not-bold",
        ),
        pytest.param(
            '<p><span style="font-style:italic">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "*a*",
            id="font-style-italic",
        ),
        pytest.param(
            '<p><span style="font-style:normal">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "a",
            id="font-style-normal-is-plain",
        ),
        pytest.param(
            '<p><span style="font-weight:bold;font-style:italic">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "***a***",
            id="bold-and-italic-combine",
        ),
        pytest.param(
            '<p><span style="font-family:Courier New">code()</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "`code()`",
            id="courier-new-is-fixed-width-code",
        ),
        pytest.param(
            '<p><span style="font-family:Consolas">x</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "`x`",
            id="consolas-is-fixed-width-code",
        ),
        pytest.param(
            '<p><span style="font-family:Arial">x</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "x",
            id="proportional-font-is-plain",
        ),
        pytest.param(
            '<p><span style="font-weight:bold;font-family:Courier New">x</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**`x`**",
            id="bold-fixed-width-nests",
        ),
        pytest.param(
            '<p><span style="font-weight:bold"><span style="color:red">x</span></span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**x**",
            id="nested-span-inherits-bold-no-double",
        ),
        pytest.param(
            '<p><span style="font-weight:bold"><span style="font-weight:bold">x</span></span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**x**",
            id="restated-bold-not-doubled",
        ),
        pytest.param(
            '<p>a<span style="font-weight:bold"> x </span>b</p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "a **x** b",
            id="inner-space-moves-outside-markers",
        ),
        pytest.param(
            '<p>keep<span style="font-weight:bold"></span> on</p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "keep on",
            id="empty-styled-span-emits-nothing",
        ),
        pytest.param(
            '<p>a <span style="text-decoration:line-through">gone</span> b</p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True), inline=Markdown.Inline(hide_strikethrough=True)),
            "a b",
            id="line-through-hidden-when-asked",
        ),
        pytest.param(
            '<p>a <span style="text-decoration:line-through">b</span> c</p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "a b c",
            id="line-through-ignored-by-default",
        ),
        pytest.param(
            '<p><span style="text-decoration:underline">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True), inline=Markdown.Inline(hide_strikethrough=True)),
            "a",
            id="underline-is-not-strikethrough",
        ),
        pytest.param(
            "<p>a <span>b</span> c</p>",
            Markdown(google=Markdown.GoogleDoc(enabled=True), inline=Markdown.Inline(hide_strikethrough=True)),
            "a b c",
            id="hide-strikethrough-with-styleless-element",
        ),
        pytest.param(
            '<p><span style="font-weight:bold">x</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True), inline=Markdown.Inline(hide_strikethrough=True)),
            "**x**",
            id="hide-strikethrough-without-text-decoration",
        ),
        pytest.param(
            '<p><span style="font-style:italic"><span style="font-style:italic">x</span></span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "*x*",
            id="nested-span-inherits-italic-no-double",
        ),
        pytest.param(
            '<p>a<span style="font-style:italic"></span>b</p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "ab",
            id="empty-italic-span-emits-nothing",
        ),
        pytest.param(
            '<p><span style="font-weight:bold;display">y</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**y**",
            id="trailing-declaration-without-colon-skipped",
        ),
        pytest.param(
            '<p><span style="font-weight:bold; :">x</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**x**",
            id="blank-name-and-value-declaration",
        ),
        pytest.param(
            '<p><span style="font-weight:bold">a</span></p>',
            Markdown(),
            "a",
            id="styles-ignored-without-google-doc",
        ),
        pytest.param(
            "<p><span>plain</span></p>",
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "plain",
            id="span-without-style-is-plain",
        ),
        pytest.param(
            '<p><span style="color:red">x</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "x",
            id="unrelated-style-property",
        ),
        pytest.param(
            '<p><span style="display;font-weight:bold">x</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**x**",
            id="declaration-without-colon-skipped",
        ),
        pytest.param(
            '<p><span style="FONT-WEIGHT: BOLD">x</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**x**",
            id="property-and-value-case-insensitive",
        ),
        pytest.param(
            '<p><span style="  font-weight : bold ">x</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "**x**",
            id="whitespace-around-property-and-value-trimmed",
        ),
        pytest.param(
            '<p><span style="font-weight:bold">a</span></p>',
            Markdown(google=Markdown.GoogleDoc(enabled=True), inline=Markdown.Inline(strong="__", emphasis="_")),
            "__a__",
            id="bold-uses-configured-marker",
        ),
        pytest.param(
            '<ul><li style="margin-left:36px">a</li><li style="margin-left:72px">b</li></ul>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "  - a\n    - b",
            id="margin-left-nests-list-items",
        ),
        pytest.param(
            '<ul><li style="margin-left:72px">a</li></ul>',
            Markdown(google=Markdown.GoogleDoc(enabled=True, list_indent=72)),
            "  - a",
            id="custom-list-indent-divisor",
        ),
        pytest.param(
            '<ol><li style="margin-left:36px">a</li></ol>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "  1. a",
            id="margin-left-nests-ordered-items",
        ),
        pytest.param(
            "<ul><li>a</li></ul>",
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "- a",
            id="list-item-without-margin-is-flat",
        ),
        pytest.param(
            '<ul><li style="margin-left:48px">x</li></ul>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "  - x",
            id="margin-not-a-multiple-floors-down",
        ),
        pytest.param(
            '<ul><li style="margin-left:36">a</li></ul>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "  - a",
            id="margin-left-without-px-unit",
        ),
        pytest.param(
            '<ul><li style="margin-left:auto">a</li></ul>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "- a",
            id="non-numeric-margin-is-no-nesting",
        ),
        pytest.param(
            '<ul><li style="margin-left:-36px">a</li></ul>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "- a",
            id="negative-margin-is-no-nesting",
        ),
        pytest.param(
            '<ul><li style="color:red">a</li></ul>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "- a",
            id="list-item-style-without-margin",
        ),
        pytest.param(
            '<ol style="list-style-type:disc"><li>a</li></ol>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "- a",
            id="list-style-disc-renders-unordered",
        ),
        pytest.param(
            '<ul style="list-style-type:decimal"><li>a</li></ul>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "1. a",
            id="list-style-decimal-renders-ordered",
        ),
        pytest.param(
            '<ul style="color:red"><li>a</li></ul>',
            Markdown(google=Markdown.GoogleDoc(enabled=True)),
            "- a",
            id="list-without-style-type-keeps-tag",
        ),
    ],
)
def test_google_doc(html: str, config: Markdown, expected: str) -> None:
    assert md(html, config) == expected


def test_google_list_indent_must_be_positive() -> None:
    with pytest.raises(ValueError, match="google_list_indent"):
        parse("<p>x</p>").to_markdown(Markdown(google=Markdown.GoogleDoc(list_indent=0)))


def test_google_doc_preset_enables_styling_and_drops_struck_text() -> None:
    preset = Markdown.google_doc()
    assert preset.google.enabled
    assert preset.inline.hide_strikethrough
    html = '<p><span style="font-weight:700">keep</span> <span style="text-decoration:line-through">gone</span></p>'
    assert parse(html).to_markdown(preset) == "**keep**"
