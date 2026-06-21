"""Main-content extraction via Node.main_content()/main_text() (the resiliparse role).

The readability content-density heuristic is pure C in treebuilder_readability.h.
These cases drive every scoring branch with article-shaped fixtures: tag and
class/id weighting, the boilerplate prunings, link-density discounting, the
candidate-array regrow, and the empty-result guards.
"""

from __future__ import annotations

import pytest

from turbohtml import Document, Element, Text, parse

# A prose paragraph: >100 chars so the length bonus saturates, with commas that
# each add a clause point, the signal that marks it as real content.
PROSE = (
    "A comet is an icy small body that, when it passes close to the Sun, warms up, "
    "begins to release gases, and forms a glowing coma, a thin atmosphere, around it."
)
# A shorter prose paragraph (>25 chars, <100) so the length bonus stays below the cap.
SHORT_PROSE = "The tail points away from the Sun."

# A very long paragraph (>300 chars) so the length bonus saturates at the cap.
LONG_PROSE = PROSE + " " + PROSE + " " + PROSE


def main_tag(html: str) -> str | None:
    found = parse(html).main_content()
    return None if found is None else found.tag


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param(
            f"<nav><a href='/'>Home</a></nav><article class=post><p>{PROSE}</p></article>"
            f"<footer><p>Copyright notice, all rights reserved here.</p></footer>",
            "article",
            id="article-beats-nav-and-footer",
        ),
        pytest.param(
            f"<div id=main-content><p>{PROSE}</p><p>{PROSE}</p></div>"
            f"<div class=sidebar><p>{PROSE}</p></div>",
            "div",
            id="content-id-beats-sidebar-class",
        ),
        pytest.param(
            f"<main><div class=entry><p>{PROSE}</p></div></main>",
            "div",
            id="positive-inner-div-wins",
        ),
    ],
)
def test_main_content_selects_article(html: str, expected: str) -> None:
    assert main_tag(html) == expected


def test_main_content_returns_element() -> None:
    found = parse(f"<article class=post><p>{PROSE}</p></article>").main_content()
    assert isinstance(found, Element)
    assert found.attrs["class"] == ["post"]


def test_main_text_renders_the_winner() -> None:
    text = parse(f"<nav><a href='/'>Home</a></nav><article class=post><h1>Comets</h1><p>{PROSE}</p></article>").main_text()
    assert text.startswith("Comets")
    assert "A comet is an icy" in text
    assert "Home" not in text


@pytest.mark.parametrize(
    "html",
    [
        pytest.param("", id="empty"),
        pytest.param("<nav><a href='/'>Home</a></nav>", id="navigation-only"),
        pytest.param("<p>Too short.</p><p>Also brief.</p>", id="only-short-paragraphs"),
        pytest.param(f"<div class=comment><p>{PROSE}</p></div>", id="unlikely-subtree-skipped"),
    ],
)
def test_no_main_content(html: str) -> None:
    doc = parse(html)
    assert doc.main_content() is None
    assert doc.main_text() == ""


def test_unlikely_subtree_rescued_by_maybe_hint() -> None:
    assert main_tag(f"<div class='comment main'><p>{PROSE}</p></div>") == "div"


def test_negative_class_loses_to_neutral_container() -> None:
    html = f"<section><p>{PROSE}</p><p>{PROSE}</p></section><div class=widget><p>{PROSE}</p><p>{PROSE}</p></div>"
    assert main_tag(html) == "section"


def test_uppercase_positive_class_matches() -> None:
    assert main_tag(f"<div class=ARTICLE><p>{PROSE}</p></div>") == "div"


def test_match_by_id_when_no_class() -> None:
    assert main_tag(f"<div id=story><p>{PROSE}</p></div>") == "div"


def test_valueless_class_attribute_is_ignored() -> None:
    assert main_tag(f"<div class id=post><p>{PROSE}</p></div>") == "div"


def test_grandparent_is_none_for_direct_paragraph_parent() -> None:
    div = parse(f"<div><p>{PROSE}</p></div>").find("div")
    assert isinstance(div, Element)
    found = div.main_content()
    assert isinstance(found, Element)
    assert found.tag == "div"


def test_score_propagates_to_grandparent() -> None:
    found = parse(f"<main><article><p>{PROSE}</p></article></main>").main_content()
    assert isinstance(found, Element)
    assert found.tag == "article"


@pytest.mark.parametrize(
    "wrapper",
    [
        pytest.param("blockquote", id="blockquote-plus-three"),
        pytest.param("li", id="li-minus-three"),
        pytest.param("form", id="form-minus-three"),
    ],
)
def test_tag_weight_containers_still_win_with_strong_prose(wrapper: str) -> None:
    html = f"<{wrapper}><p>{PROSE}</p><p>{PROSE}</p></{wrapper}>"
    assert main_tag(html) == wrapper


def test_table_cell_paragraph_scores() -> None:
    # A <td> is itself a paragraph tag, so its combined text rolls up to the <tr>,
    # which outscores the cell; the cell is still seeded as a candidate (tag weight +3).
    html = f"<table><tr><td><p>{PROSE}</p><p>{PROSE}</p></td></tr></table>"
    assert main_tag(html) == "tr"


def test_heading_cell_negative_weight_can_still_win() -> None:
    html = f"<table><tr><th><p>{PROSE}</p><p>{PROSE}</p></th></tr></table>"
    assert main_tag(html) == "th"


def test_high_link_density_candidate_is_discounted_to_nothing() -> None:
    long_link = "Read the full story, the complete report, and the appendix, all linked over here now"
    assert parse(f"<div><p><a href='/x'>{long_link}</a></p></div>").main_content() is None


def test_link_text_lowers_but_does_not_eliminate_prose() -> None:
    html = f"<article class=post><p>{PROSE} <a href='/u'>see more</a></p><p>{PROSE}</p></article>"
    assert main_tag(html) == "article"


def test_foreign_namespace_subtree_is_skipped() -> None:
    html = f"<svg><text>vector caption text goes here in the drawing</text></svg><article class=post><p>{PROSE}</p></article>"
    assert main_tag(html) == "article"


def test_embedded_skip_tags_do_not_count_as_text() -> None:
    html = (
        "<article class=post><p>Real prose, with a clause, sits beside noise here, plenty of words to count."
        "<script>var junk = 1;</script><svg><text>vector</text></svg></p></article>"
    )
    found = parse(html).main_content()
    assert isinstance(found, Element)
    assert "var junk" not in found.main_text()


def test_comment_and_nested_anchor_markup_inside_prose() -> None:
    html = (
        f"<article class=post><p>{PROSE}<!--editor note--> and a link "
        f"<a href='/u'>to the <b>full</b> report here, with details</a></p><p>{PROSE}</p></article>"
    )
    found = parse(html).main_content()
    assert isinstance(found, Element)
    assert found.tag == "article"
    assert "editor note" not in found.main_text()


def test_empty_text_node_counts_as_zero_length() -> None:
    article = Element("article", {"class": "post"})
    paragraph = Element("p")
    paragraph.append(Text(PROSE))
    paragraph.append(Text(""))
    article.append(paragraph)
    found = article.main_content()
    assert isinstance(found, Element)
    assert found.tag == "article"


def test_short_paragraph_below_threshold_is_noise() -> None:
    html = f"<div class=post><p>tiny</p></div><div class=entry><p>{PROSE}</p><p>{PROSE}</p></div>"
    found = parse(html).main_content()
    assert isinstance(found, Element)
    assert found.attrs["class"] == ["entry"]


def test_short_prose_scores_without_length_bonus() -> None:
    assert main_tag(f"<article class=post><p>{SHORT_PROSE}</p><p>{SHORT_PROSE}</p></article>") == "article"


def test_very_long_paragraph_saturates_the_length_bonus() -> None:
    assert main_tag(f"<article class=post><p>{LONG_PROSE}</p></article>") == "article"


def test_many_candidates_grow_the_array() -> None:
    sections = "".join(f"<section><div class=entry><p>{PROSE}</p></div></section>" for _ in range(8))
    found = parse(f"<body>{sections}</body>").main_content()
    assert isinstance(found, Element)
    assert found.tag in {"div", "section"}


def test_methods_exist_on_document_and_element() -> None:
    doc = parse(f"<article class=post><p>{PROSE}</p></article>")
    assert isinstance(doc, Document)
    body = doc.find("body")
    assert isinstance(body, Element)
    assert body.main_content() is not None
