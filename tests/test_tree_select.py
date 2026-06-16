"""CSS selectors: select() / select_one() over the common selector subset."""

from __future__ import annotations

import pytest

from turbohtml import parse

_DOC = (
    '<section id="s" class="box wide">'
    '<h2 class="title">T</h2>'
    '<p class="lead first">one <a href="/x" rel="next">link</a></p>'
    "<p>two</p>"
    '<ul><li class="item">a</li><li class="item sel">b</li></ul>'
    '<my-widget data-k="v" lang="en-US">w</my-widget>'
    "</section>"
)


def _sel(html: str, selector: str) -> list[str]:
    return [element.tag for element in parse(html).select(selector)]


@pytest.mark.parametrize(
    ("selector", "tags"),
    [
        # simple selectors
        pytest.param("li", ["li", "li"], id="type"),
        pytest.param(".item", ["li", "li"], id="class"),
        pytest.param("#s", ["section"], id="id"),
        pytest.param("my-widget", ["my-widget"], id="unknown-tag-by-name"),
        pytest.param("li.sel", ["li"], id="compound-type-class"),
        pytest.param("p.lead.first", ["p"], id="compound-two-classes"),
        # attribute operators
        pytest.param("[rel]", ["a"], id="exists"),
        pytest.param('[href="/x"]', ["a"], id="equals"),
        pytest.param('[class~="wide"]', ["section"], id="includes"),
        pytest.param('[lang|="en"]', ["my-widget"], id="dash"),
        pytest.param('[href^="/"]', ["a"], id="prefix"),
        pytest.param('[href$="x"]', ["a"], id="suffix"),
        pytest.param('[href*="/x"]', ["a"], id="substring"),
        pytest.param('[lang="EN-us" i]', ["my-widget"], id="case-insensitive"),
        pytest.param('[lang="EN-us" s]', [], id="case-sensitive"),
        pytest.param("[data-missing]", [], id="name-absent-in-tree"),
        pytest.param("[rel=nope]", [], id="value-mismatch"),
        pytest.param("[rel='next']", ["a"], id="single-quoted"),
        pytest.param("[CLASS]", ["section", "h2", "p", "li", "li"], id="uppercase-name"),
        # attribute operator near misses
        pytest.param('[href^="z"]', [], id="prefix-miss"),
        pytest.param('[href^="/xyz"]', [], id="prefix-too-long"),
        pytest.param('[href$="z"]', [], id="suffix-miss"),
        pytest.param('[href$="//xx"]', [], id="suffix-too-long"),
        pytest.param('[href*="zz"]', [], id="substring-miss"),
        pytest.param('[lang|="en-US"]', ["my-widget"], id="dash-exact"),
        pytest.param('[lang|="en-U"]', [], id="dash-no-boundary"),
        pytest.param('[lang|="en-US-x"]', [], id="dash-prefix-too-long"),
        pytest.param('[lang|="xx"]', [], id="dash-prefix-mismatch-at-boundary"),
        pytest.param('[class~="zzz"]', [], id="includes-miss"),
        # empty operand never matches the prefix/suffix/substring/includes ops
        pytest.param('[href^=""]', [], id="prefix-empty"),
        pytest.param('[href$=""]', [], id="suffix-empty"),
        pytest.param('[href*=""]', [], id="substring-empty"),
        pytest.param('[class~=""]', [], id="includes-empty"),
        # non-ASCII attribute names are not present, so they match nothing
        pytest.param("[café]", [], id="latin1-name"),
        pytest.param("[中]", [], id="bmp-name"),
        pytest.param("[😀]", [], id="astral-name"),
        # combinators
        pytest.param("section a", ["a"], id="descendant"),
        pytest.param("ul > li", ["li", "li"], id="child"),
        pytest.param("section > a", [], id="child-not-direct"),
        pytest.param("h2 + p", ["p"], id="adjacent-sibling"),
        pytest.param("p + h2", [], id="adjacent-no-preceding-element"),
        pytest.param("h2 ~ p", ["p", "p"], id="general-sibling"),
        pytest.param("table ~ p", [], id="general-sibling-no-preceding"),
        pytest.param("h2 ~ ul", ["ul"], id="general-sibling-scans-past-non-matches"),
        pytest.param("div > ul > li", [], id="child-chain-breaks-above-match"),
        pytest.param("h2 + ul", [], id="adjacent-compound-miss"),
        # grouping
        pytest.param("h2, a", ["h2", "a"], id="comma-group-in-document-order"),
        pytest.param("#nope", [], id="id-present-but-mismatched"),
        # the encode buffers cap tag names at 60 bytes and attribute names at 124;
        # a longer name overruns the cap and cannot match any real element
        pytest.param("z" * 130, [], id="overlong-tag-name"),
        pytest.param("[" + "z" * 130 + "]", [], id="overlong-attr-name"),
    ],
)
def test_select_over_doc(selector: str, tags: list[str]) -> None:
    assert _sel(_DOC, selector) == tags


@pytest.mark.parametrize(
    ("html", "selector", "tags"),
    [
        pytest.param("<div></div>text<p>x</p>", "div + p", ["p"], id="adjacent-skips-text-node"),
        # the nearest <div> ancestor has no matching <i>, but a higher one does
        pytest.param(
            "<div class=x><i><div class=y><b>hit</b></div></i></div>", ".x i b", ["b"], id="descendant-backtracks-hit"
        ),
        pytest.param(
            "<div class=x><i><div class=y><b>hit</b></div></i></div>", ".y i b", [], id="descendant-backtracks-miss"
        ),
        # span's preceding p siblings: pick one whose own preceding sibling is an h1
        pytest.param(
            "<h1>a</h1><p class=x>b</p><h1>c</h1><p>d</p><span>e</span>",
            "p ~ span",
            ["span"],
            id="general-sibling-backtracks",
        ),
        # the near <p> fails its left context (an <a> sits before it); the scan
        # continues to the far <p>, whose preceding element is the <i>
        pytest.param(
            "<i></i><p>1</p><a></a><p>2</p><span>x</span>",
            "i + p ~ span",
            ["span"],
            id="general-sibling-backtracks-left-context",
        ),
        # span's previous element p matches, but p's previous element is x, not i
        pytest.param("<x></x><p>p</p><span>s</span>", "i + p + span", [], id="adjacent-chain-misses"),
        pytest.param("<input disabled>", "[disabled]", ["input"], id="valueless-exists"),
        pytest.param("<input disabled>", '[disabled=""]', ["input"], id="valueless-empty-equals"),
        pytest.param("<input disabled>", "[disabled=x]", [], id="valueless-value-mismatch"),
        pytest.param("<div id>", "#x", [], id="valueless-id-matches-nothing"),
        pytest.param("<div class>", ".x", [], id="valueless-class-matches-nothing"),
        pytest.param("<DIV></DIV>", "DIV", ["div"], id="type-folds-case"),
        pytest.param('<div class="a_b">', ".a_b", ["div"], id="class-underscore"),
        pytest.param('<div class="café">', ".café", ["div"], id="class-non-ascii"),
        pytest.param("<café>x", "café", ["café"], id="type-non-ascii"),
        # a token followed by whitespace running to the end of the value still matches
        pytest.param('<div class="a ">', ".a", ["div"], id="trailing-whitespace-class-hit"),
        pytest.param('<div data-x="a ">', '[data-x~="a"]', ["div"], id="trailing-whitespace-attr-hit"),
        # a trailing whitespace run is consumed without yielding an empty token, so
        # the scan reaches the end with no match, exercising the loop-exit branches
        pytest.param('<div class="a ">', ".zzz", [], id="trailing-whitespace-class-miss"),
        pytest.param('<div data-x="a ">', '[data-x~="zzz"]', [], id="trailing-whitespace-attr-miss"),
    ],
)
def test_select_over_custom_html(html: str, selector: str, tags: list[str]) -> None:
    assert _sel(html, selector) == tags


def test_universal_under_a_root() -> None:
    assert (section := parse(_DOC).select_one("section")) is not None
    assert len(section.select("*")) == 8  # h2, p, a, p, ul, li, li, my-widget


def test_select_is_scoped_to_descendants() -> None:
    assert (section := parse(_DOC).select_one("section")) is not None
    assert section.select("section") == []  # the receiver itself is not a descendant


def test_select_one() -> None:
    assert (match := parse(_DOC).select_one("p.lead")) is not None
    assert match.text.startswith("one")
    assert parse(_DOC).select_one("table") is None


@pytest.mark.parametrize(
    "selector",
    [
        pytest.param("", id="empty"),
        pytest.param("  ", id="whitespace"),
        pytest.param(".", id="bare-dot"),
        pytest.param("#", id="bare-hash"),
        pytest.param("p..", id="double-dot"),
        pytest.param("p >", id="dangling-combinator"),
        pytest.param("p,", id="trailing-comma"),
        pytest.param("[", id="open-bracket"),
        pytest.param("[a", id="unterminated-attr"),
        pytest.param("[a=]", id="missing-value"),
        pytest.param('[a="x]', id="unterminated-string"),
        pytest.param("[a!=b]", id="bad-operator"),
        pytest.param("[a~b]", id="tilde-without-equals"),
        pytest.param("[a~", id="operator-at-eof"),
        pytest.param("[a=", id="value-then-eof"),
        pytest.param("[a=b", id="value-at-eof"),
        pytest.param("[a=b c]", id="junk-after-value"),
        pytest.param("p!", id="trailing-junk"),
        pytest.param("p !", id="whitespace-then-junk"),
        pytest.param("p" + ".x" * 40, id="too-many-simples"),
        pytest.param(" ".join(["a"] * 40), id="too-many-compounds"),
        pytest.param(",".join(["a"] * 70), id="too-many-groups"),
    ],
)
def test_invalid_selectors_raise(selector: str) -> None:
    with pytest.raises(ValueError, match="selector"):
        parse(_DOC).select(selector)


def test_select_one_rejects_invalid_selector() -> None:
    with pytest.raises(ValueError, match="selector"):
        parse(_DOC).select_one("[")


@pytest.mark.parametrize("method", [pytest.param("select", id="select"), pytest.param("select_one", id="select_one")])
def test_rejects_non_str(method: str) -> None:
    with pytest.raises(TypeError):
        getattr(parse(_DOC), method)(123)
