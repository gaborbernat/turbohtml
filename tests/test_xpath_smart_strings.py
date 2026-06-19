"""``smart_strings`` xpath results, mirroring lxml's ``_ElementUnicodeResult``.

By default an attribute or ``text()`` value is a plain ``str`` (turbohtml's fast
path, also what parsel uses). With ``smart_strings=True`` it is an
:class:`~turbohtml.XPathString` that remembers its origin element.
"""

from __future__ import annotations

import pytest

import turbohtml
from turbohtml import Element, XPathString

HTML = "<html><body><a href='/x' class='c'>link</a></body></html>"


@pytest.fixture
def doc() -> turbohtml.Node:
    return turbohtml.parse(HTML)


def test_default_is_a_plain_string(doc: turbohtml.Node) -> None:
    result = doc.xpath("//a/@href")[0]
    assert type(result) is str
    assert result == "/x"


def test_smart_strings_false_is_a_plain_string(doc: turbohtml.Node) -> None:
    result = doc.xpath("//a/@href", smart_strings=False)[0]
    assert type(result) is str


def test_a_plain_variable_keyword_does_not_enable_smart_strings(doc: turbohtml.Node) -> None:
    # kwargs present but no smart_strings key: the result stays a plain str.
    result = doc.xpath("//a[@href=$h]/@href", h="/x")[0]
    assert type(result) is str


def test_smart_attribute_remembers_its_element(doc: turbohtml.Node) -> None:
    result = doc.xpath("//a/@href", smart_strings=True)[0]
    assert isinstance(result, XPathString)
    assert result == "/x"
    assert result.is_attribute is True
    assert result.is_text is False
    assert result.is_tail is False
    assert result.attrname == "href"
    parent = result.getparent()
    assert isinstance(parent, Element)
    assert parent.tag == "a"


def test_smart_text_remembers_its_element(doc: turbohtml.Node) -> None:
    result = doc.xpath("//a/text()", smart_strings=True)[0]
    assert isinstance(result, XPathString)
    assert result == "link"
    assert result.is_text is True
    assert result.is_attribute is False
    assert result.attrname is None
    assert result.getparent().tag == "a"


def test_smart_strings_alongside_a_variable(doc: turbohtml.Node) -> None:
    # smart_strings is consumed as an option; h is still bound as a $variable.
    result = doc.xpath("//a[@href=$h]/@href", h="/x", smart_strings=True)[0]
    assert isinstance(result, XPathString)
    assert result.getparent().tag == "a"


def test_smart_strings_through_xpath_one(doc: turbohtml.Node) -> None:
    result = doc.xpath_one("//a/@class", smart_strings=True)
    assert isinstance(result, XPathString)
    assert result.attrname == "class"


def test_smart_strings_through_xpath_iter(doc: turbohtml.Node) -> None:
    results = list(doc.xpath_iter("//a/@href", smart_strings=True))
    assert all(isinstance(result, XPathString) for result in results)
