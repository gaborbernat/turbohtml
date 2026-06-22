"""Article extraction via Node.article() (the trafilatura / newspaper3k role).

The content scoring reuses the readability heuristic; these cases drive the
metadata harvesting beside it -- title, byline, date, description and lang, each
with its present, absent, and multiple-source-precedence behavior, plus the
whitespace normalization and the no-content result.
"""

from __future__ import annotations

import pytest

from turbohtml import Article, Document, Element, parse, parse_fragment

PROSE = (
    "A comet is an icy small body that, when it passes close to the Sun, warms up, "
    "begins to release gases, and forms a glowing coma, a thin atmosphere, around it."
)
BODY = f"<article class=post><p>{PROSE}</p></article>"


def test_returns_article_record() -> None:
    art = parse(f"<html lang=en><body>{BODY}</body></html>").article()
    assert isinstance(art, Article)
    assert isinstance(art.element, Element)
    assert art.element.tag == "article"
    assert "A comet is an icy" in art.text
    assert art.lang == "en"


def test_no_content_yields_none_element_and_empty_text() -> None:
    art = parse("<title>Just a title</title><p>Too short.</p>").article()
    assert art.element is None
    assert not art.text
    assert art.title == "Just a title"


def test_metadata_present_without_content() -> None:
    art = parse("<html lang=fr><head><title>Solo</title></head><body><p>brief</p></body></html>").article()
    assert art.element is None
    assert art.title == "Solo"
    assert art.lang == "fr"


def test_all_fields_absent_are_none() -> None:
    art = parse(f"<body>{BODY}</body>").article()
    assert art.title is None
    assert art.byline is None
    assert art.date is None
    assert art.description is None


def test_available_on_element() -> None:
    body = parse(f"<html lang=en><body>{BODY}</body></html>").find("body")
    assert isinstance(body, Element)
    art = body.article()
    assert isinstance(art.element, Element)
    assert art.element.tag == "article"


def test_programmatic_element_without_html_has_no_lang() -> None:
    article = Element("article", {"class": "post"})
    paragraph = Element("p")
    paragraph.append(Element("span"))
    article.append(paragraph)
    art = article.article()
    assert art.lang is None
    assert art.title is None


# --- title -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "body", "expected"),
    [
        pytest.param(
            "<title>Page</title><meta property=og:title content='Social'>",
            "<h1>Heading</h1>",
            "Heading",
            id="h1-wins",
        ),
        pytest.param(
            "<title>Page</title><meta property=og:title content='Social'>",
            "",
            "Social",
            id="og-title-when-no-h1",
        ),
        pytest.param("<title>Page</title>", "", "Page", id="title-element-last"),
        pytest.param(
            "<meta property=og:title content='Social'>",
            "<h1>   </h1>",
            "Social",
            id="blank-h1-falls-through",
        ),
    ],
)
def test_title_precedence(head: str, body: str, expected: str) -> None:
    art = parse(f"<html><head>{head}</head><body>{body}{BODY}</body></html>").article()
    assert art.title == expected


# --- byline ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "body", "expected"),
    [
        pytest.param(
            "<meta name=author content='Meta Author'>",
            "<a rel='nofollow author' href='/u'>Link Author</a>",
            "Link Author",
            id="rel-author-link-wins",
        ),
        pytest.param(
            "<meta name=author content='Meta Author'><meta property=article:author content='Article Author'>",
            "",
            "Meta Author",
            id="meta-author-when-no-link",
        ),
        pytest.param(
            "<meta property=article:author content='Article Author'>",
            "",
            "Article Author",
            id="article-author-last",
        ),
    ],
)
def test_byline_precedence(head: str, body: str, expected: str) -> None:
    art = parse(f"<html><head>{head}</head><body>{body}{BODY}</body></html>").article()
    assert art.byline == expected


def test_byline_ignores_non_author_rel() -> None:
    art = parse(f"<body><a rel='nofollow noopener ' href='/x'>Nope</a>{BODY}</body>").article()
    assert art.byline is None


def test_rel_author_with_leading_whitespace_matches() -> None:
    art = parse(f"<body><a rel=' author' href='/u'>Padded</a>{BODY}</body>").article()
    assert art.byline == "Padded"


def test_byline_skips_anchor_without_rel() -> None:
    art = parse(f"<head><meta name=author content='Meta'></head><body><a href='/x'>Plain</a>{BODY}</body>").article()
    assert art.byline == "Meta"


def test_empty_rel_author_link_falls_through_to_meta() -> None:
    art = parse(
        f"<head><meta name=author content='Meta'></head><body><a rel=author href='/u'></a>{BODY}</body>"
    ).article()
    assert art.byline == "Meta"


# --- date ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "body", "expected"),
    [
        pytest.param(
            "<meta property=article:published_time content='2020-01-01'>",
            "<time datetime='2024-05-06'>May 6</time>",
            "2024-05-06",
            id="time-datetime-wins",
        ),
        pytest.param("", "<time>March 2024</time>", "March 2024", id="time-text-when-no-datetime"),
        pytest.param(
            "<meta property=article:published_time content='2020-01-01'>",
            "",
            "2020-01-01",
            id="published-time-meta",
        ),
        pytest.param("<meta name=date content='2019-12-31'>", "", "2019-12-31", id="common-date-meta"),
        pytest.param("<meta name=pubdate content='2018-11-30'>", "", "2018-11-30", id="pubdate-meta"),
        pytest.param("<meta name=dc.date content='2017-10-29'>", "", "2017-10-29", id="dc-date-meta"),
    ],
)
def test_date_precedence(head: str, body: str, expected: str) -> None:
    art = parse(f"<html><head>{head}</head><body>{body}{BODY}</body></html>").article()
    assert art.date == expected


def test_valueless_datetime_falls_back_to_time_text() -> None:
    art = parse(f"<body><time datetime>April 2024</time>{BODY}</body>").article()
    assert art.date == "April 2024"


def test_date_empty_time_falls_through_to_meta() -> None:
    html = (
        f"<html><head><meta name=date content='2016-01-01'></head><body><time datetime=''> </time>{BODY}</body></html>"
    )
    assert parse(html).article().date == "2016-01-01"


# --- description -----------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        pytest.param(
            "<meta name=description content='Plain desc'><meta property=og:description content='OG desc'>",
            "OG desc",
            id="og-description-wins",
        ),
        pytest.param("<meta name=description content='Plain desc'>", "Plain desc", id="meta-description-fallback"),
    ],
)
def test_description_precedence(head: str, expected: str) -> None:
    art = parse(f"<html><head>{head}</head><body>{BODY}</body></html>").article()
    assert art.description == expected


def test_description_absent_is_none() -> None:
    assert parse(f"<body>{BODY}</body>").article().description is None


# --- lang ------------------------------------------------------------------


def test_lang_present() -> None:
    assert parse(f"<html lang='en-US'><body>{BODY}</body></html>").article().lang == "en-US"


def test_lang_absent_is_none() -> None:
    assert parse(f"<html><body>{BODY}</body></html>").article().lang is None


def test_valueless_lang_attribute_is_absent() -> None:
    assert parse(f"<html lang><body>{BODY}</body></html>").article().lang is None


def test_fragment_without_html_element_has_no_lang() -> None:
    fragment = parse_fragment(f"<article class=post><p>{PROSE}</p></article>", "div")
    art = fragment.article()
    assert isinstance(art.element, Element)
    assert art.lang is None


# --- normalization ---------------------------------------------------------


def test_whitespace_is_collapsed_and_trimmed() -> None:
    art = parse(f"<body><h1>\n  Comets\t and\f  Tails  \n</h1>{BODY}</body>").article()
    assert art.title == "Comets and Tails"


def test_foreign_elements_and_valueless_meta_are_skipped() -> None:
    html = (
        "<html lang=en><head><meta name>"
        "<meta property=og:title content='Real'>"
        "<meta property=og:description content='Desc'></head>"
        f"<body><svg><title>vector</title><a>link</a></svg>{BODY}</body></html>"
    )
    art = parse(html).article()
    assert art.title == "Real"
    assert art.description == "Desc"
    assert art.byline is None


def test_metadata_keys_match_case_insensitively() -> None:
    html = (
        "<head><meta property='OG:TITLE' content='Cased'></head>"
        f"<body><a rel='AUTHOR' href='/u'>Cased Author</a>{BODY}</body>"
    )
    art = parse(html).article()
    assert art.title == "Cased"
    assert art.byline == "Cased Author"


def test_meta_property_and_name_both_match() -> None:
    by_property = parse(f"<head><meta property=description content='via property'></head><body>{BODY}</body>")
    by_name = parse(f"<head><meta name=description content='via name'></head><body>{BODY}</body>")
    assert by_property.article().description == "via property"
    assert by_name.article().description == "via name"


def test_meta_without_content_attribute_is_skipped() -> None:
    html = f"<html><head><meta property=og:title><title>Real</title></head><body>{BODY}</body></html>"
    assert parse(html).article().title == "Real"


def test_meta_with_valueless_content_is_skipped() -> None:
    html = f"<html><head><meta property=og:title content><title>Fallback</title></head><body>{BODY}</body></html>"
    assert parse(html).article().title == "Fallback"


def test_article_fields_unpack_in_order() -> None:
    art = parse(f"<html lang=en><body>{BODY}</body></html>").article()
    element, text, title, byline, date, description, lang = art
    assert element is art.element
    assert text is art.text
    assert (title, byline, date, description, lang) == (
        art.title,
        art.byline,
        art.date,
        art.description,
        art.lang,
    )


def test_document_and_element_agree_on_metadata() -> None:
    doc = parse(f"<html lang=en><head><title>T</title></head><body>{BODY}</body></html>")
    assert isinstance(doc, Document)
    body = doc.find("body")
    assert isinstance(body, Element)
    assert doc.article().lang == body.article().lang == "en"
