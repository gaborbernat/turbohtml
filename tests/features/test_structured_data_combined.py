from __future__ import annotations

import pytest

from turbohtml import Document, MicrodataItem, StructuredData, parse

_RICH = (
    '<head><meta property="og:title" content="T"></head>'
    '<body><script type="application/ld+json">{"@type": "Thing"}</script>'
    '<div itemscope><span itemprop="name">Ada</span></div></body>'
)


@pytest.fixture
def rich() -> Document:
    return parse(_RICH)


def test_structured_data_record(rich: Document) -> None:
    assert rich.structured_data() == StructuredData(
        json_ld=[{"@type": "Thing"}],
        microdata=[MicrodataItem(type=None, id=None, properties={"name": ["Ada"]})],
        opengraph={"og:title": "T"},
        microformats=[],
        rdfa=[],
    )


def test_fields_match_per_format_helpers(rich: Document) -> None:
    data = rich.structured_data()
    assert data.json_ld == rich.json_ld()
    assert data.microdata == rich.microdata()
    assert data.opengraph == rich.opengraph()


def test_record_is_read_only(rich: Document) -> None:
    data = rich.structured_data()
    field = "json_ld"
    with pytest.raises(AttributeError):
        setattr(data, field, [])


def test_empty_document() -> None:
    assert parse("<p>nothing</p>").structured_data() == StructuredData(
        json_ld=[],
        microdata=[],
        opengraph={},
        microformats=[],
        rdfa=[],
    )
