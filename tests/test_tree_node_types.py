"""Doctype identifiers and structural pattern matching across the node hierarchy."""

from __future__ import annotations

import pytest

from turbohtml import Doctype, Document, Element, parse


def _doctype(markup: str) -> Doctype:
    node = parse(markup).children[0]  # the doctype is the document's first child
    assert isinstance(node, Doctype)
    return node


@pytest.mark.parametrize(
    ("markup", "public_id", "system_id"),
    [
        pytest.param("<!DOCTYPE html>", None, None, id="name-only"),
        pytest.param(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">',
            "-//W3C//DTD HTML 4.01//EN",
            "http://www.w3.org/TR/html4/strict.dtd",
            id="public-and-system",
        ),
        pytest.param(
            '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN">',
            "-//W3C//DTD HTML 4.01//EN",
            "",
            id="public-only-empty-system",
        ),
        pytest.param(
            '<!DOCTYPE html SYSTEM "about:legacy-compat">',
            "",
            "about:legacy-compat",
            id="system-only-empty-public",
        ),
    ],
)
def test_doctype_identifiers(markup: str, public_id: str | None, system_id: str | None) -> None:
    doctype = _doctype(markup)
    assert doctype.name == "html"
    assert doctype.public_id == public_id
    assert doctype.system_id == system_id


def test_doctype_matches_on_name() -> None:
    match _doctype("<!DOCTYPE html>"):
        case Doctype(name):
            assert name == "html"
        case _:  # pragma: no cover - the doctype always matches
            pytest.fail("doctype did not match")


def test_document_matches_on_root() -> None:
    match parse("<title>t</title>"):
        case Document(Element(tag)):
            assert tag == "html"
        case _:  # pragma: no cover - a parsed document always has an html root
            pytest.fail("document did not match")
