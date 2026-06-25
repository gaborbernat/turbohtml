"""The to_markdown() output modes added for issue #219.

Word wrapping (wrap_width / wrap_list_items / wrap_links), raw-HTML passthrough
for images and tables (image_mode="html", table_mode="html"), and prose
transliteration to ASCII. One golden case per behavior so every new C path is
exercised.
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
            "<p>one two three four five six seven eight</p>",
            Markdown(wrapping=Markdown.Wrapping(width=15)),
            "one two three\nfour five six\nseven eight",
            id="wrap-prose-greedy",
        ),
        pytest.param(
            "<p>antidisestablishmentarianism rocks</p>",
            Markdown(wrapping=Markdown.Wrapping(width=10)),
            "antidisestablishmentarianism\nrocks",
            id="wrap-long-word-not-split",
        ),
        pytest.param(
            "<blockquote>alpha beta gamma delta</blockquote>",
            Markdown(wrapping=Markdown.Wrapping(width=12)),
            "> alpha beta\n> gamma\n> delta",
            id="wrap-keeps-blockquote-prefix",
        ),
        pytest.param(
            "<p>one two three</p>",
            Markdown(wrapping=Markdown.Wrapping(width=0)),
            "one two three",
            id="wrap-zero-disables",
        ),
    ],
)
def test_wrap_width(html: str, config: Markdown, expected: str) -> None:
    assert md(html, config) == expected


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        pytest.param(
            Markdown(wrapping=Markdown.Wrapping(width=12)),
            "- alpha beta gamma delta epsilon",
            id="list-items-unwrapped-by-default",
        ),
        pytest.param(
            Markdown(wrapping=Markdown.Wrapping(width=12, list_items=True)),
            "- alpha beta\n  gamma\n  delta\n  epsilon",
            id="list-items-wrapped",
        ),
    ],
)
def test_wrap_list_items(config: Markdown, expected: str) -> None:
    html = "<ul><li>alpha beta gamma delta epsilon</li></ul>"
    assert md(html, config) == expected


@pytest.mark.parametrize(
    ("html", "config", "expected"),
    [
        pytest.param(
            '<p>see <a href="u">the long link text here</a> ok</p>',
            Markdown(wrapping=Markdown.Wrapping(width=10, links=False)),
            "see [the long link text here](u)\nok",
            id="links-unbroken",
        ),
        pytest.param(
            '<p><a href="u">alpha beta gamma</a></p>',
            Markdown(wrapping=Markdown.Wrapping(width=10)),
            "[alpha\nbeta gamma](u)",
            id="links-wrap-when-allowed",
        ),
    ],
)
def test_wrap_links(html: str, config: Markdown, expected: str) -> None:
    assert md(html, config) == expected


@pytest.mark.parametrize(
    ("html", "config", "expected"),
    [
        pytest.param(
            '<p><img src="a.png" alt="x" width="4"></p>',
            Markdown(images=Markdown.Images(mode="html")),
            '<img src="a.png" alt="x" width="4">',
            id="image-html-keeps-attributes",
        ),
        pytest.param(
            "<table><tr><td>a</td></tr></table>",
            Markdown(tables=Markdown.Tables(mode="html")),
            "<table><tbody><tr><td>a</td></tr></tbody></table>",
            id="table-html-verbatim",
        ),
    ],
)
def test_html_passthrough(html: str, config: Markdown, expected: str) -> None:
    assert md(html, config) == expected


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param("<p>café naïve</p>", "cafe naive", id="accented-latin1"),
        pytest.param("<p>œuvre Œ ß</p>", "oeuvre OE ss", id="latin-extended-a"),
        pytest.param("<p>“q” \u2018r\u2019 — … ©</p>", "\"q\" 'r' -- ... (C)", id="punctuation-and-symbols"),
        pytest.param("<p>a → b ← c \u00d7 d</p>", "a -> b <- c x d", id="arrows-and-times"),
        pytest.param("<p>中文 é</p>", "中文 e", id="unmapped-non-ascii-passthrough"),
    ],
)
def test_transliterate(html: str, expected: str) -> None:
    assert md(html, Markdown(document=Markdown.Document(transliterate=True))) == expected


def test_transliterate_leaves_code_verbatim() -> None:
    assert md("<p><code>café</code></p>", Markdown(document=Markdown.Document(transliterate=True))) == "`café`"


def test_wrap_and_transliterate_compose() -> None:
    html = "<p>The “quick” brown fox — jumps over the lazy dog today.</p>"
    expected = 'The "quick" brown fox -- jumps\nover the lazy dog today.'
    config = Markdown(wrapping=Markdown.Wrapping(width=30), document=Markdown.Document(transliterate=True))
    assert md(html, config) == expected


def test_wrap_width_rejects_negative() -> None:
    with pytest.raises(ValueError, match="wrap_width"):
        parse("<p>x</p>").to_markdown(Markdown(wrapping=Markdown.Wrapping(width=-1)))


@pytest.mark.parametrize(
    ("config", "option"),
    [
        # a bogus enum value on purpose, to exercise the renderer's runtime validation
        pytest.param(
            Markdown(images=Markdown.Images(mode="bogus")),  # ty: ignore[invalid-argument-type]
            "image_mode",
            id="image_mode",
        ),
        pytest.param(
            Markdown(tables=Markdown.Tables(mode="bogus")),  # ty: ignore[invalid-argument-type]
            "table_mode",
            id="table_mode",
        ),
    ],
)
def test_new_enum_values_still_validate(config: Markdown, option: str) -> None:
    with pytest.raises(ValueError, match=option):
        parse("<p>x</p>").to_markdown(config)
