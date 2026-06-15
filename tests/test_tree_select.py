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


# --- simple selectors ---


def test_type() -> None:
    assert _sel(_DOC, "li") == ["li", "li"]


def test_universal_under_a_root() -> None:
    section = parse(_DOC).select_one("section")
    assert section is not None
    assert len(section.select("*")) == 8  # h2, p, a, p, ul, li, li, my-widget


def test_class() -> None:
    assert _sel(_DOC, ".item") == ["li", "li"]


def test_id() -> None:
    assert _sel(_DOC, "#s") == ["section"]


def test_unknown_tag_matches_by_name() -> None:
    assert _sel(_DOC, "my-widget") == ["my-widget"]


def test_compound() -> None:
    assert _sel(_DOC, "li.sel") == ["li"]
    assert _sel(_DOC, "p.lead.first") == ["p"]


# --- attribute operators ---


@pytest.mark.parametrize(
    ("selector", "tags"),
    [
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
        # operator near misses
        pytest.param('[href^="z"]', [], id="prefix-miss"),
        pytest.param('[href^="/xyz"]', [], id="prefix-too-long"),
        pytest.param('[href$="z"]', [], id="suffix-miss"),
        pytest.param('[href$="//xx"]', [], id="suffix-too-long"),
        pytest.param('[href*="zz"]', [], id="substring-miss"),
        pytest.param('[lang|="en-US"]', ["my-widget"], id="dash-exact"),
        pytest.param('[lang|="en-U"]', [], id="dash-no-boundary"),
        pytest.param('[lang|="en-US-x"]', [], id="dash-prefix-too-long"),
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
    ],
)
def test_attribute_operators(selector: str, tags: list[str]) -> None:
    assert _sel(_DOC, selector) == tags


def test_valueless_attribute() -> None:
    assert _sel("<input disabled>", "[disabled]") == ["input"]
    assert _sel("<input disabled>", '[disabled=""]') == ["input"]  # empty equals an empty value
    assert _sel("<input disabled>", "[disabled=x]") == []


def test_valueless_id_and_class_match_nothing() -> None:
    assert _sel("<div id>", "#x") == []
    assert _sel("<div class>", ".x") == []


def test_uppercase_and_non_ascii_names() -> None:
    assert _sel("<DIV></DIV>", "DIV") == ["div"]  # type selectors fold case
    assert _sel('<div class="a_b">', ".a_b") == ["div"]
    assert _sel('<div class="café">', ".café") == ["div"]
    assert _sel("<café>x", "café") == ["café"]  # an unknown non-ASCII type name


def test_token_scan_skips_trailing_whitespace() -> None:
    # a token followed by whitespace running to the end of the value still matches
    assert _sel('<div class="a ">', ".a") == ["div"]
    assert _sel('<div data-x="a ">', '[data-x~="a"]') == ["div"]
    # a trailing run of whitespace is consumed without yielding an empty token: the
    # scan reaches the end with no match, exercising the loop-exit branches
    assert _sel('<div class="a ">', ".zzz") == []
    assert _sel('<div data-x="a ">', '[data-x~="zzz"]') == []


# --- combinators ---


def test_descendant() -> None:
    assert _sel(_DOC, "section a") == ["a"]


def test_child() -> None:
    assert _sel(_DOC, "ul > li") == ["li", "li"]
    assert _sel(_DOC, "section > a") == []  # a is not a direct child of section


def test_adjacent_sibling() -> None:
    assert _sel(_DOC, "h2 + p") == ["p"]


def test_adjacent_sibling_skips_text_node() -> None:
    # the text between </div> and <p> is skipped when finding the preceding element
    assert _sel("<div></div>text<p>x</p>", "div + p") == ["p"]


def test_adjacent_sibling_no_preceding_element() -> None:
    # h2 is the first child of section, so it has no preceding sibling element
    assert _sel(_DOC, "p + h2") == []


def test_general_sibling() -> None:
    assert _sel(_DOC, "h2 ~ p") == ["p", "p"]


def test_general_sibling_no_match_in_preceding() -> None:
    assert _sel(_DOC, "table ~ p") == []  # no preceding <table> sibling exists


def test_general_sibling_scans_past_non_matches() -> None:
    # ul's preceding siblings are p, p, h2; the scan walks past both <p> to the <h2>
    assert _sel(_DOC, "h2 ~ ul") == ["ul"]


def test_descendant_backtracks() -> None:
    # the nearest <div> ancestor of the <b> has no matching <i>, a higher one does
    html = "<div class=x><i><div class=y><b>hit</b></div></i></div>"
    assert _sel(html, ".x i b") == ["b"]
    assert _sel(html, ".y i b") == []


def test_general_sibling_backtracks() -> None:
    html = "<h1>a</h1><p class=x>b</p><h1>c</h1><p>d</p><span>e</span>"
    # span's preceding p siblings: pick one whose own preceding sibling is an h1
    assert _sel(html, "p ~ span") == ["span"]


def test_general_sibling_backtracks_past_failed_left_context() -> None:
    # span ~ p finds the near <p> first, but its left context (i + p) fails because
    # an <a> sits before it; the scan continues to the far <p>, whose preceding
    # element is the <i>, satisfying the whole chain
    html = "<i></i><p>1</p><a></a><p>2</p><span>x</span>"
    assert _sel(html, "i + p ~ span") == ["span"]


# --- grouping and select_one ---


def test_comma_groups_in_document_order() -> None:
    assert _sel(_DOC, "h2, a") == ["h2", "a"]


def test_select_one() -> None:
    match = parse(_DOC).select_one("p.lead")
    assert match is not None
    assert match.text.startswith("one")
    assert parse(_DOC).select_one("table") is None


def test_select_is_scoped_to_descendants() -> None:
    section = parse(_DOC).select_one("section")
    assert section is not None
    assert section.select("section") == []  # the receiver itself is not a descendant


# --- syntax errors ---


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


def test_selector_must_be_a_str() -> None:
    with pytest.raises(TypeError):
        parse(_DOC).select(123)  # ty: ignore[invalid-argument-type]  # not a str


def test_select_one_rejects_non_str() -> None:
    with pytest.raises(TypeError):
        parse(_DOC).select_one(123)  # ty: ignore[invalid-argument-type]  # not a str


def test_select_one_rejects_invalid_selector() -> None:
    with pytest.raises(ValueError, match="selector"):
        parse(_DOC).select_one("[")
