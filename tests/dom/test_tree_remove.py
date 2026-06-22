"""Node.remove: drop every descendant subtree matching a CSS selector."""

from __future__ import annotations

import pytest

from turbohtml import Document, Element, parse


def _body(document: Document) -> Element:
    """The body element of a parsed document, asserted present."""
    body = document.select_one("body")
    assert body is not None
    return body


def test_drops_a_single_match_and_its_subtree() -> None:
    document = parse("<main><article>text<b>bold</b></article><p>keep</p></main>")
    document.remove("article")
    assert _body(document).serialize() == "<body><main><p>keep</p></main></body>"


def test_drops_each_of_several_matches() -> None:
    document = parse("<ul><li class=off>a</li><li>b</li><li class=off>c</li></ul>")
    document.remove("li.off")
    assert _body(document).serialize() == "<body><ul><li>b</li></ul></body>"


def test_keeps_unrelated_siblings_and_text() -> None:
    document = parse("<main>loose<!--c--><aside>drop</aside>more</main>")
    document.remove("aside")
    assert _body(document).serialize() == "<body><main>loose<!--c-->more</main></body>"


def test_descendant_combinator_uses_the_full_matcher() -> None:
    document = parse("<main><section><article>in</article></section><article>out</article></main>")
    document.remove("section article")
    assert _body(document).serialize() == "<body><main><section></section><article>out</article></main></body>"


def test_nested_match_inside_a_removed_match_drops_harmlessly() -> None:
    document = parse("<div class=drop><span class=drop>x</span><i>y</i></div><p>stay</p>")
    document.remove(".drop")
    assert _body(document).serialize() == "<body><p>stay</p></body>"


def test_grows_the_snapshot_buffer_for_many_matches() -> None:
    items = "".join(f"<li class=x>{index}</li>" for index in range(20))
    document = parse(f"<ul>{items}<li>keep</li></ul>")
    container = document.select_one("ul")
    assert container is not None
    container.remove("li.x")
    assert [item.text for item in container.select("li")] == ["keep"]


def test_no_match_leaves_the_subtree_untouched() -> None:
    document = parse("<main><p>a</p><p>b</p></main>")
    main = document.select_one("main")
    assert main is not None
    main.remove("article")
    assert main.serialize() == "<main><p>a</p><p>b</p></main>"


def test_removes_relative_to_the_node_it_is_called_on() -> None:
    document = parse("<section><p class=hit>x</p></section><p class=hit>y</p>")
    section = document.select_one("section")
    assert section is not None
    section.remove(".hit")
    assert section.serialize() == "<section></section>"
    assert _body(document).serialize() == '<body><section></section><p class="hit">y</p></body>'


def test_is_the_inverse_of_prune() -> None:
    markup = "<main><article>keep</article><aside>drop</aside></main>"
    pruned = parse(markup)
    pruned.prune("aside")
    removed = parse(markup)
    removed.remove("article")
    assert _body(pruned).serialize() == "<body><main><aside>drop</aside></main></body>"
    assert _body(removed).serialize() == "<body><main><aside>drop</aside></main></body>"


def test_returns_the_node_for_chaining() -> None:
    document = parse("<main><article>a</article></main>")
    assert document.remove("article") is document


def test_rejects_a_non_str_selector() -> None:
    document = parse("<p>x</p>")
    with pytest.raises(TypeError):
        getattr(document, "remove")(123)  # noqa: B009  # getattr keeps the bad arg from the type checker


def test_rejects_an_invalid_selector() -> None:
    with pytest.raises(ValueError, match="selector"):
        parse("<p>x</p>").remove("[")
