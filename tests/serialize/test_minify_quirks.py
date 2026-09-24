"""Minified output keeps the document mode: a quirks-mode reparse nests a <table> in an
open <p>, so the doctype that picks the mode and the </p> before a table both matter."""

from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Doctype, Element, Html, Minify, parse
from turbohtml.clean import minify

_TRANSITIONAL: Final = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">'


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("<p>x</p><table></table>", "<p>x</p><table></table>", id="no-doctype-keeps-end-tag"),
        pytest.param(
            f"{_TRANSITIONAL}<p>x</p><table></table>",
            '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"><p>x</p><table></table>',
            id="quirky-doctype-keeps-end-tag",
        ),
        pytest.param(
            f"{_TRANSITIONAL}<p>x<table></table>",
            '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"><p>x<table></table>',
            id="quirky-doctype-keeps-nested-table",
        ),
        pytest.param(
            "<!DOCTYPE html><p>x</p><table></table>", "<!DOCTYPE html><p>x<table></table>", id="no-quirks-omits-end-tag"
        ),
    ],
)
def test_minify_p_before_table(source: str, expected: str) -> None:
    assert minify(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("<!DOCTYPE html>", "<!DOCTYPE html>", id="name-only"),
        pytest.param(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">',
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">',
            id="public-and-system",
        ),
        pytest.param(
            '<!DOCTYPE html SYSTEM "about:legacy-compat">', '<!DOCTYPE html SYSTEM "about:legacy-compat">', id="system"
        ),
        pytest.param('<!DOCTYPE html PUBLIC "" "">', '<!DOCTYPE html PUBLIC "" "">', id="empty-identifiers"),
        pytest.param('<!DOCTYPE html PUBLIC "a\'b">', '<!DOCTYPE html PUBLIC "a\'b">', id="apostrophe"),
        pytest.param("<!DOCTYPE html PUBLIC 'a\"b'>", "<!DOCTYPE html PUBLIC 'a\"b'>", id="double-quote"),
        pytest.param("<!DOCTYPE html bogus>", "<!DOCTYPE html x>", id="forced-quirks-name"),
        pytest.param('<!DOCTYPE html PUBLIC "a>', '<!DOCTYPE html PUBLIC "a>', id="forced-quirks-public"),
        pytest.param('<!DOCTYPE html PUBLIC "a" "b>', '<!DOCTYPE html PUBLIC "a" "b>', id="forced-quirks-system"),
        pytest.param('<!DOCTYPE html SYSTEM "b>', '<!DOCTYPE html SYSTEM "b>', id="forced-quirks-system-only"),
        pytest.param("<!DOCTYPE foo bogus>", "<!DOCTYPE foo>", id="quirky-name-needs-no-force"),
    ],
)
def test_minify_doctype(source: str, expected: str) -> None:
    assert minify(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(f"{_TRANSITIONAL}<p>x<table><tr><td>a</td></tr></table>", id="transitional"),
        pytest.param("<!DOCTYPE html bogus><p>x<table>", id="forced-quirks"),
        pytest.param('<!DOCTYPE html PUBLIC "a" "b><p>x<table>', id="forced-quirks-system"),
    ],
)
def test_minify_quirks_document_reparses_same(source: str) -> None:
    once: Final = minify(source)
    assert (parse(once).html, minify(once)) == (parse(source).html, once)


def _doctype(source: str) -> Doctype:
    node = parse(source).children[0]
    assert isinstance(node, Doctype)
    return node


def test_minify_document_without_doctype_keeps_end_tag() -> None:
    document: Final = parse("<!DOCTYPE html><p>x</p><table></table>")
    _ = document.children[0].extract()
    assert "x</p><table>" in document.serialize(Html(layout=Minify()))


def test_minify_document_with_adopted_quirky_doctype_keeps_end_tag() -> None:
    document: Final = parse("<!DOCTYPE html><p>x</p><table></table>")
    document.children[0].replace_with(_doctype("<!DOCTYPE foo>"))
    assert "x</p><table>" in document.serialize(Html(layout=Minify()))


def test_minify_element_in_no_quirks_tree_omits_end_tag() -> None:
    body: Final = parse("<!DOCTYPE html><body><p>x</p><table></table>").select_one("body")
    assert isinstance(body, Element)
    assert body.serialize(Html(layout=Minify())) == "<body><p>x<table></table></body>"
