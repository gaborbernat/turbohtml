from __future__ import annotations

import pytest

from turbohtml import MicrodataItem, parse

_BY_TAG = (
    "<div itemscope>"
    '<meta itemprop="meta" content="MC">'
    '<img itemprop="img" src="i.png">'
    '<a itemprop="a" href="/l">x</a>'
    '<object itemprop="obj" data="/d"></object>'
    '<data itemprop="data" value="42">forty</data>'
    '<meter itemprop="meter" value="7"></meter>'
    '<time itemprop="t1" datetime="2020-01-01">Jan</time>'
    '<time itemprop="t2">Feb</time>'
    '<time itemprop="t3" datetime>Mar</time>'
    '<span itemprop="text">plain text</span>'
    '<img itemprop="nosrc">'
    '<data itemprop="noval" value>z</data>'
    "</div>"
)

_NESTED = (
    '<div itemscope itemtype="https://schema.org/Person">'
    '<span itemprop="name">Ada</span>'
    '<div itemprop="address" itemscope itemtype="https://schema.org/PostalAddress">'
    '<span itemprop="city">London</span>'
    "</div>"
    "</div>"
)


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        pytest.param(
            '<div itemscope><span itemprop="name">Ada</span></div>',
            [MicrodataItem(type=None, id=None, properties={"name": ["Ada"]})],
            id="simple-text-property",
        ),
        pytest.param(
            '<div itemscope itemtype="https://schema.org/Thing https://schema.org/Person"></div>',
            [MicrodataItem(type="https://schema.org/Thing https://schema.org/Person", id=None, properties={})],
            id="itemtype-verbatim",
        ),
        pytest.param(
            '<div itemscope itemtype><span itemprop="a">x</span></div>',
            [MicrodataItem(type=None, id=None, properties={"a": ["x"]})],
            id="valueless-itemtype-is-none",
        ),
        pytest.param(
            '<div itemscope itemid="urn:isbn:1" itemtype="https://schema.org/Book"><span itemprop="n">B</span></div>',
            [MicrodataItem(type="https://schema.org/Book", id="urn:isbn:1", properties={"n": ["B"]})],
            id="itemid",
        ),
        pytest.param(
            '<div itemscope itemid><span itemprop="a">x</span></div>',
            [MicrodataItem(type=None, id=None, properties={"a": ["x"]})],
            id="valueless-itemid-is-none",
        ),
        pytest.param(
            '<div itemscope><span itemprop="a b">v</span></div>',
            [MicrodataItem(type=None, id=None, properties={"a": ["v"], "b": ["v"]})],
            id="multiple-names-share-value",
        ),
        pytest.param(
            '<div itemscope><span itemprop="x">1</span><span itemprop="x">2</span></div>',
            [MicrodataItem(type=None, id=None, properties={"x": ["1", "2"]})],
            id="repeated-name-collects-values",
        ),
        pytest.param(
            _BY_TAG,
            [
                MicrodataItem(
                    type=None,
                    id=None,
                    properties={
                        "meta": ["MC"],
                        "img": ["i.png"],
                        "a": ["/l"],
                        "obj": ["/d"],
                        "data": ["42"],
                        "meter": ["7"],
                        "t1": ["2020-01-01"],
                        "t2": ["Feb"],
                        "t3": ["Mar"],
                        "text": ["plain text"],
                        "nosrc": [""],
                        "noval": [""],
                    },
                ),
            ],
            id="property-values-by-tag",
        ),
        pytest.param(
            _NESTED,
            [
                MicrodataItem(
                    type="https://schema.org/Person",
                    id=None,
                    properties={
                        "name": ["Ada"],
                        "address": [
                            MicrodataItem(
                                type="https://schema.org/PostalAddress",
                                id=None,
                                properties={"city": ["London"]},
                            ),
                        ],
                    },
                ),
            ],
            id="nested-item",
        ),
        pytest.param(
            '<div itemscope><p><span itemprop="wrapped">W</span></p></div>',
            [MicrodataItem(type=None, id=None, properties={"wrapped": ["W"]})],
            id="property-inside-non-itemprop-wrapper",
        ),
        pytest.param(
            '<div itemscope><span itemprop>a</span><span itemprop="">b</span><span itemprop="real">c</span></div>',
            [MicrodataItem(type=None, id=None, properties={"real": ["c"]})],
            id="valueless-and-empty-itemprop-are-not-properties",
        ),
        pytest.param('<span itemscope itemprop="x">orphan</span>', [], id="itemscope-with-itemprop-not-top-level"),
        pytest.param("<p>nothing here</p>", [], id="no-microdata"),
    ],
)
def test_microdata(html: str, expected: list[MicrodataItem]) -> None:
    assert parse(html).microdata() == expected
