"""Node.strip_tags: unwrap every descendant matching a CSS selector in place."""

from __future__ import annotations

import pytest

from turbohtml import Document, Element, parse


def _body(document: Document) -> Element:
    """The body element of a parsed document, asserted present."""
    body = document.select_one("body")
    assert body is not None
    return body


def test_unwraps_a_single_match_keeping_its_children() -> None:
    document = parse("<p>a <b>bold</b> z</p>")
    document.strip_tags("b")
    assert _body(document).serialize() == "<body><p>a bold z</p></body>"


def test_unwraps_each_of_several_matches() -> None:
    document = parse("<p><span>one</span> and <span>two</span></p>")
    document.strip_tags("span")
    assert _body(document).serialize() == "<body><p>one and two</p></body>"


def test_unwraps_a_match_with_element_children() -> None:
    document = parse("<div class=wrap><p>x</p><p>y</p></div>")
    document.strip_tags(".wrap")
    assert _body(document).serialize() == "<body><p>x</p><p>y</p></body>"


def test_unwraps_an_empty_match_by_just_dropping_it() -> None:
    document = parse("<p>a<span></span>b</p>")
    document.strip_tags("span")
    assert _body(document).serialize() == "<body><p>ab</p></body>"


def test_nested_matches_collapse_to_the_inner_content() -> None:
    document = parse("<p><b><i>x</i></b></p>")
    document.strip_tags("b, i")
    assert _body(document).serialize() == "<body><p>x</p></body>"


def test_descendant_combinator_uses_the_full_matcher() -> None:
    document = parse("<main><section><b>in</b></section><b>out</b></main>")
    document.strip_tags("section b")
    assert _body(document).serialize() == "<body><main><section>in</section><b>out</b></main></body>"


def test_grows_the_snapshot_buffer_for_many_matches() -> None:
    spans = "".join(f"<span>{index}</span>" for index in range(20))
    document = parse(f"<p>{spans}</p>")
    paragraph = document.select_one("p")
    assert paragraph is not None
    paragraph.strip_tags("span")
    assert paragraph.select("span") == []
    assert paragraph.text == "".join(str(index) for index in range(20))


def test_no_match_leaves_the_subtree_untouched() -> None:
    document = parse("<p>a<b>x</b></p>")
    paragraph = document.select_one("p")
    assert paragraph is not None
    paragraph.strip_tags("i")
    assert paragraph.serialize() == "<p>a<b>x</b></p>"


def test_strips_relative_to_the_node_it_is_called_on() -> None:
    document = parse("<section><b>in</b></section><b>out</b>")
    section = document.select_one("section")
    assert section is not None
    section.strip_tags("b")
    assert section.serialize() == "<section>in</section>"
    assert _body(document).serialize() == "<body><section>in</section><b>out</b></body>"


def test_is_the_bulk_form_of_unwrap() -> None:
    bulk = parse("<p><b>x</b></p>")
    bulk.strip_tags("b")
    single = parse("<p><b>x</b></p>")
    bold = single.select_one("b")
    assert bold is not None
    bold.unwrap()
    assert _body(bulk).serialize() == "<body><p>x</p></body>"
    assert _body(single).serialize() == "<body><p>x</p></body>"


def test_returns_the_node_for_chaining() -> None:
    document = parse("<p><b>x</b></p>")
    assert document.strip_tags("b") is document


def test_rejects_a_non_str_selector() -> None:
    document = parse("<p>x</p>")
    with pytest.raises(TypeError):
        getattr(document, "strip_tags")(123)  # noqa: B009  # getattr keeps the bad arg from the type checker


def test_rejects_an_invalid_selector() -> None:
    with pytest.raises(ValueError, match="selector"):
        parse("<p>x</p>").strip_tags("[")
