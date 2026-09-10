from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse, parse_fragment


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("a", id="ascii"),
        pytest.param("é", id="latin1"),
        pytest.param("名", id="ucs2"),
        pytest.param("😀", id="ucs4"),
    ],
)
@pytest.mark.parametrize("fragment", [pytest.param(False, id="document"), pytest.param(True, id="fragment")])
@pytest.mark.parametrize("locations", [pytest.param(False, id="no-locations"), pytest.param(True, id="locations")])
def test_normalized_text_survives_temporary_input_and_detachment(text: str, *, fragment: bool, locations: bool) -> None:
    paragraph: Final = (
        parse_fragment(f"<p>{text}\r\n{text}\r{text}</p><p>\0</p>", "div", source_locations=locations)
        if fragment
        else parse(f"<p>{text}\r\n{text}\r{text}</p><p>\0</p>", source_locations=locations)
    ).find("p")
    assert paragraph is not None
    paragraph.extract()
    assert (paragraph.parent, paragraph.text, paragraph.html) == (
        None,
        f"{text}\n{text}\n{text}",
        f"<p>{text}\n{text}\n{text}</p>",
    )


@pytest.mark.parametrize("tag", ["script", "style", "textarea"])
def test_normalized_text_keeps_raw_text_newlines(tag: str) -> None:
    element: Final = parse(f"<{tag}>left\r\nright\r</{tag}>").find(tag)
    assert element is not None
    assert element.text == "left\nright\n"
