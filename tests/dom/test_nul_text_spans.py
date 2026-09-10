from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("a", id="ascii"),
        pytest.param("é", id="latin1"),
        pytest.param("名", id="ucs2"),
        pytest.param("😀", id="ucs4"),
    ],
)
@pytest.mark.parametrize("locations", [pytest.param(False, id="no-locations"), pytest.param(True, id="locations")])
def test_nul_text_preserves_clean_runs_and_source_positions(text: str, *, locations: bool) -> None:
    clean: Final = text * 80
    source: Final = (
        f"<p>first\0{text}</p>\n<p>{clean}</p><script>{clean}</script>"
        f"<textarea>\n{clean}</textarea><svg>{text}\0{text}</svg>"
    )
    document: Final = parse(source, positions=locations, source_locations=locations)
    assert [(element.tag, element.text) for element in document.select("p, script, textarea, svg")] == [
        ("p", f"first{text}"),
        ("p", clean),
        ("script", clean),
        ("textarea", clean),
        ("svg", f"{text}\ufffd{text}"),
    ]
    assert document.find_all("p")[1].position == ((2, 0) if locations else None)


@pytest.mark.parametrize("tag", ["script", "style", "textarea"])
def test_nul_text_keeps_raw_text_replacement(tag: str) -> None:
    root: Final = parse(f"<p>before\0after</p><{tag}>left\0right</{tag}><p>clean</p>")
    element: Final = root.find(tag)
    assert element is not None
    assert element.text == "left\ufffdright"
