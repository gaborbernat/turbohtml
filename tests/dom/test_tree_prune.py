"""Node.prune: trim a parsed tree to the subtrees matching a CSS selector."""

from __future__ import annotations

import pytest

from turbohtml import Document, Element, parse


def _body(document: Document) -> Element:
    """The body element of a parsed document, asserted present."""
    body = document.select_one("body")
    assert body is not None
    return body


def test_keeps_match_and_drops_unrelated_siblings() -> None:
    document = parse("<body><nav>skip</nav><main><article>keep</article><aside>drop</aside></main></body>")
    document.prune("article")
    assert _body(document).serialize() == "<body><main><article>keep</article></main></body>"


def test_keeps_the_whole_subtree_under_a_match() -> None:
    document = parse("<main><article>text<b>bold</b><span>more</span></article><p>gone</p></main>")
    document.prune("article")
    assert (
        _body(document).serialize() == "<body><main><article>text<b>bold</b><span>more</span></article></main></body>"
    )


def test_keeps_each_of_several_matches() -> None:
    document = parse("<ul><li class=on>a</li><li>b</li><li class=on>c</li></ul>")
    document.prune("li.on")
    assert _body(document).serialize() == '<body><ul><li class="on">a</li><li class="on">c</li></ul></body>'


def test_descendant_combinator_uses_the_full_matcher() -> None:
    document = parse("<main><section><article>in</article></section><article>out</article></main>")
    document.prune("section article")
    assert _body(document).serialize() == "<body><main><section><article>in</article></section></main></body>"


def test_nested_matches_keep_the_outer_whole_subtree() -> None:
    document = parse("<div class=keep><span class=keep>x</span><i>y</i></div><div>drop</div>")
    document.prune(".keep")
    assert _body(document).serialize() == '<body><div class="keep"><span class="keep">x</span><i>y</i></div></body>'


def test_grows_the_keep_buffer_for_many_matches() -> None:
    items = "".join(f"<li class=x>{index}</li>" for index in range(20))
    document = parse(f"<ul>{items}</ul>")
    container = document.select_one("ul")
    assert container is not None
    container.prune("li.x")
    assert len(container.select("li")) == 20


def test_no_match_empties_the_subtree() -> None:
    document = parse("<main><p>a</p><p>b</p></main>")
    main = document.select_one("main")
    assert main is not None
    main.prune("article")
    assert main.serialize() == "<main></main>"


def test_no_match_on_the_document_root_empties_everything() -> None:
    document = parse("<main><p>a</p></main>")
    document.prune("article")
    assert document.select_one("html") is None


def test_removes_text_and_comment_nodes_outside_a_match() -> None:
    document = parse("<main>loose<!--c--><article>keep</article>more</main>")
    document.prune("article")
    assert _body(document).serialize() == "<body><main><article>keep</article></main></body>"


def test_prunes_relative_to_the_node_it_is_called_on() -> None:
    document = parse("<section><h1>title</h1><div><p class=hit>x</p><p>y</p></div></section>")
    section = document.select_one("section")
    assert section is not None
    section.prune(".hit")
    assert section.serialize() == '<section><div><p class="hit">x</p></div></section>'


def test_returns_the_node_for_chaining() -> None:
    document = parse("<main><article>a</article></main>")
    assert document.prune("article") is document


def test_keeps_a_deep_match_through_its_ancestor_chain() -> None:
    markup = "<main><section><article class=keep>deep</article></section><aside>drop</aside></main>"
    document = parse(markup)
    document.prune(".keep")
    assert (
        _body(document).serialize()
        == '<body><main><section><article class="keep">deep</article></section></main></body>'
    )


def test_rejects_a_non_str_selector() -> None:
    document = parse("<p>x</p>")
    with pytest.raises(TypeError):
        getattr(document, "prune")(123)  # noqa: B009  # getattr keeps the bad arg from the type checker


def test_rejects_an_invalid_selector() -> None:
    with pytest.raises(ValueError, match="selector"):
        parse("<p>x</p>").prune("[")
