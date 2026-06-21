"""The strip/convert tag filters of Node.to_markdown().

``strip`` names tags whose markup is dropped while their text stays; ``convert``
names the only tags to keep markup for, so every other tag is dropped. The two
are mutually exclusive. The cases pin the inline and block unwrapping, the
allowlist/denylist semantics, and the binding's argument handling and errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turbohtml import parse

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from turbohtml import Document


@pytest.mark.parametrize(
    ("html", "strip", "expected"),
    [
        pytest.param(
            '<p>visit <a href="https://e.test">the site</a> today</p>',
            ["a"],
            "visit the site today",
            id="link-loses-markup",
        ),
        pytest.param("<p>a <b>bold</b> and <i>soft</i></p>", ["b"], "a bold and *soft*", id="one-of-two"),
        pytest.param("<p>a <b>bold</b> and <i>soft</i></p>", ["b", "i"], "a bold and soft", id="both"),
        pytest.param("<p>a <b>bold</b> and <i>soft</i></p>", ["i"], "a **bold** and soft", id="other-kept"),
    ],
)
def test_strip_inline(html: str, strip: list[str], expected: str) -> None:
    assert parse(html).to_markdown(strip=strip) == expected


@pytest.mark.parametrize(
    ("html", "convert", "expected"),
    [
        pytest.param(
            '<p>a <b>bold</b> and <a href="https://e.test">link</a></p>',
            ["a"],
            "a bold and [link](https://e.test)",
            id="only-link-kept",
        ),
        pytest.param(
            '<p>a <b>bold</b> and <a href="https://e.test">link</a></p>',
            ["b"],
            "a **bold** and link",
            id="only-bold-kept",
        ),
        pytest.param("<p>a <b>bold</b> and <i>soft</i></p>", ["b", "i"], "a **bold** and *soft*", id="both-kept"),
    ],
)
def test_convert_inline(html: str, convert: list[str], expected: str) -> None:
    assert parse(html).to_markdown(convert=convert) == expected


def test_convert_empty_drops_all_markup() -> None:
    # an empty allowlist keeps markup for nothing, so only the text survives
    out = parse('<p><b>x</b> <a href="https://e.test">y</a></p>').to_markdown(convert=[])
    assert out == "x y"


def test_strip_block_keeps_children() -> None:
    out = parse("<blockquote><p>quoted</p></blockquote>").to_markdown(strip=["blockquote"])
    assert out == "quoted"


def test_strip_heading_unwraps_to_prose() -> None:
    out = parse("<h2>Heading</h2><p>Body text.</p>").to_markdown(strip=["h2"])
    assert out == "Heading\n\nBody text."


def test_convert_block_drops_outer_block() -> None:
    out = parse("<blockquote><p>kept</p></blockquote>").to_markdown(convert=["p"])
    assert out == "kept"


def test_strip_leaves_foreign_element_untouched() -> None:
    # an SVG element has no HTML atom, so it is never named by a filter and renders normally
    out = parse("<p>a <svg><title>chart</title></svg> b</p>").to_markdown(strip=["b"])
    assert out == "a chart b"


@pytest.mark.parametrize(
    "render",
    [
        pytest.param(lambda doc: doc.to_markdown(strip=["script"]), id="strip"),
        pytest.param(lambda doc: doc.to_markdown(convert=["b"]), id="convert"),
    ],
)
def test_skipped_tag_inside_kept_inline_vanishes_whole(render: Callable[[Document], str]) -> None:
    # a <script> nested in a kept inline parent is reached by the inline walk, yet still
    # drops content-and-all rather than unwrapping the way the filter unwraps other tags
    assert render(parse("<p>a <b><script>var x = 1</script>keep</b> b</p>")) == "a **keep** b"


def test_uppercase_tag_name_is_lowercased() -> None:
    # a tag name is matched case-insensitively, exercising the ASCII lowercasing
    out = parse("<p><b>x</b></p>").to_markdown(strip=["B"])
    assert out == "x"


def test_unknown_tag_name_is_ignored() -> None:
    html = "<p><b>x</b></p>"
    assert parse(html).to_markdown(strip=["nosuchtag"]) == parse(html).to_markdown()


def test_overlong_tag_name_is_ignored() -> None:
    html = "<p><b>x</b></p>"
    assert parse(html).to_markdown(strip=["z" * 65]) == parse(html).to_markdown()


def test_surrogate_tag_name_is_ignored() -> None:
    html = "<p><b>x</b></p>"
    assert parse(html).to_markdown(strip=["\ud800"]) == parse(html).to_markdown()


@pytest.mark.parametrize(
    "render",
    [
        pytest.param(lambda doc: doc.to_markdown(strip=None), id="strip-none"),
        pytest.param(lambda doc: doc.to_markdown(convert=None), id="convert-none"),
        pytest.param(lambda doc: doc.to_markdown(strip=[]), id="strip-empty"),
    ],
)
def test_no_op_filters_match_default(render: Callable[[Document], str]) -> None:
    html = "<p><b>x</b> <i>y</i></p>"
    assert render(parse(html)) == parse(html).to_markdown()


def test_non_str_iterable_accepted() -> None:
    out = parse("<p><b>x</b></p>").to_markdown(strip=(tag for tag in ["b"]))
    assert out == "x"


def test_strip_and_convert_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="strip and convert are mutually exclusive"):
        parse("<p><b>x</b></p>").to_markdown(strip=["b"], convert=["b"])


@pytest.mark.parametrize(
    "render",
    [
        pytest.param(lambda doc: doc.to_markdown(strip="b"), id="strip"),
        pytest.param(lambda doc: doc.to_markdown(convert="a"), id="convert"),
    ],
)
def test_single_str_rejected(render: Callable[[Document], str]) -> None:
    with pytest.raises(TypeError, match="iterable of tag names, not a single str"):
        render(parse("<p><b>x</b></p>"))


@pytest.mark.parametrize(
    "render",
    [
        # a non-iterable on purpose, to exercise the binding's iterator coercion
        pytest.param(lambda doc: doc.to_markdown(strip=42), id="strip"),
        pytest.param(lambda doc: doc.to_markdown(convert=42), id="convert"),
    ],
)
def test_non_iterable_rejected(render: Callable[[Document], str]) -> None:
    with pytest.raises(TypeError):
        render(parse("<p><b>x</b></p>"))


def test_non_str_tag_rejected() -> None:
    with pytest.raises(TypeError, match="tags must be str, not int"):
        # a non-str element on purpose, to exercise the per-item type check
        parse("<p><b>x</b></p>").to_markdown(strip=["b", 5])  # ty: ignore[invalid-argument-type]


def test_iterator_error_propagates() -> None:
    def tags() -> Iterator[str]:
        yield "b"
        msg = "boom"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="boom"):
        parse("<p><b>x</b></p>").to_markdown(strip=tags())
