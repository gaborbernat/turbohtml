"""The to_markdown() output modes added for issue #219.

Word wrapping (wrap_width / wrap_list_items / wrap_links), raw-HTML passthrough
for images and tables (image_mode="html", table_mode="html"), and prose
transliteration to ASCII. One golden case per behavior so every new C path is
exercised.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Literal


class _Opts(TypedDict, total=False):
    """The to_markdown options touched by the new output modes, kept typed."""

    wrap_width: int
    wrap_list_items: bool
    wrap_links: bool
    transliterate: bool
    image_mode: Literal["markdown", "alt", "ignore", "html"]
    table_mode: Literal["markdown", "strip", "html"]


def md(html: str, opts: _Opts) -> str:
    return parse(html).to_markdown(**opts)


def call_with(convert: Callable[..., str], **kwargs: str | int) -> str:
    """Invoke a converter with arguments the static signature would reject, to
    drive the runtime validation; the converter arrives signature-erased."""
    return convert(**kwargs)


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param(
            "<p>one two three four five six seven eight</p>",
            _Opts(wrap_width=15),
            "one two three\nfour five six\nseven eight",
            id="wrap-prose-greedy",
        ),
        pytest.param(
            "<p>antidisestablishmentarianism rocks</p>",
            _Opts(wrap_width=10),
            "antidisestablishmentarianism\nrocks",
            id="wrap-long-word-not-split",
        ),
        pytest.param(
            "<blockquote>alpha beta gamma delta</blockquote>",
            _Opts(wrap_width=12),
            "> alpha beta\n> gamma\n> delta",
            id="wrap-keeps-blockquote-prefix",
        ),
        pytest.param(
            "<p>one two three</p>",
            _Opts(wrap_width=0),
            "one two three",
            id="wrap-zero-disables",
        ),
    ],
)
def test_wrap_width(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("opts", "expected"),
    [
        pytest.param(_Opts(wrap_width=12), "- alpha beta gamma delta epsilon", id="list-items-unwrapped-by-default"),
        pytest.param(
            _Opts(wrap_width=12, wrap_list_items=True),
            "- alpha beta\n  gamma\n  delta\n  epsilon",
            id="list-items-wrapped",
        ),
    ],
)
def test_wrap_list_items(opts: _Opts, expected: str) -> None:
    html = "<ul><li>alpha beta gamma delta epsilon</li></ul>"
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param(
            '<p>see <a href="u">the long link text here</a> ok</p>',
            _Opts(wrap_width=10, wrap_links=False),
            "see [the long link text here](u)\nok",
            id="links-unbroken",
        ),
        pytest.param(
            '<p><a href="u">alpha beta gamma</a></p>',
            _Opts(wrap_width=10),
            "[alpha\nbeta gamma](u)",
            id="links-wrap-when-allowed",
        ),
    ],
)
def test_wrap_links(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "opts", "expected"),
    [
        pytest.param(
            '<p><img src="a.png" alt="x" width="4"></p>',
            _Opts(image_mode="html"),
            '<img src="a.png" alt="x" width="4">',
            id="image-html-keeps-attributes",
        ),
        pytest.param(
            "<table><tr><td>a</td></tr></table>",
            _Opts(table_mode="html"),
            "<table><tbody><tr><td>a</td></tr></tbody></table>",
            id="table-html-verbatim",
        ),
    ],
)
def test_html_passthrough(html: str, opts: _Opts, expected: str) -> None:
    assert md(html, opts) == expected


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param("<p>café naïve</p>", "cafe naive", id="accented-latin1"),
        pytest.param("<p>œuvre Œ ß</p>", "oeuvre OE ss", id="latin-extended-a"),
        pytest.param("<p>“q” ‘r’ — … ©</p>", '"q" \'r\' -- ... (C)', id="punctuation-and-symbols"),
        pytest.param("<p>a → b ← c × d</p>", "a -> b <- c x d", id="arrows-and-times"),
        pytest.param("<p>中文 é</p>", "中文 e", id="unmapped-non-ascii-passthrough"),
    ],
)
def test_transliterate(html: str, expected: str) -> None:
    assert md(html, _Opts(transliterate=True)) == expected


def test_transliterate_leaves_code_verbatim() -> None:
    assert md("<p><code>café</code></p>", _Opts(transliterate=True)) == "`café`"


def test_wrap_and_transliterate_compose() -> None:
    html = "<p>The “quick” brown fox — jumps over the lazy dog today.</p>"
    expected = 'The "quick" brown fox -- jumps\nover the lazy dog today.'
    assert md(html, _Opts(wrap_width=30, transliterate=True)) == expected


def test_wrap_width_rejects_negative() -> None:
    with pytest.raises(ValueError, match="wrap_width"):
        call_with(parse("<p>x</p>").to_markdown, wrap_width=-1)


@pytest.mark.parametrize("option", ["image_mode", "table_mode"])
def test_new_enum_values_still_validate(option: str) -> None:
    with pytest.raises(ValueError, match=option):
        call_with(parse("<p>x</p>").to_markdown, **{option: "bogus"})
