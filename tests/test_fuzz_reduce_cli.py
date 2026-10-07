"""Reduced finding artifacts retain the original public oracle result."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

import pytest
from fuzz.round_trip_oracles import ORACLES, Floor, Oracle, main
from tinycss2 import parse_stylesheet, serialize

from turbohtml import parse_fragment

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("source", "syntax", "expected"),
    [
        pytest.param("<div><aside>noise</aside><p>x</p></div>", "html", "<div><p>x</p></div>", id="html-subtree"),
        pytest.param("p{color:red;margin:1px;}", "css", "p{margin:1px;}", id="css-declaration"),
    ],
)
def test_reduce_cli_saves_structural_finding(
    mocker: MockerFixture, tmp_path: Path, source: str, syntax: Literal["html", "css"], expected: str
) -> None:
    def check(text: str) -> str | None:
        if syntax == "html":
            return "retained" if parse_fragment(text).serialize(inner=True) == text and "x" in text else None
        return (
            "retained"
            if text.startswith("p{") and serialize(parse_stylesheet(text)) == text and "margin:1px;" in text
            else None
        )

    mocker.patch.dict(
        ORACLES,
        {
            "probe": Oracle(
                check, lambda _rng: source, lambda: [source], lambda: {"control": True}, Floor(1, 1), syntax=syntax
            )
        },
        clear=True,
    )
    code = main(["--minutes", "0", "--crash-dir", str(tmp_path)])
    artifacts = [path.read_text() for path in tmp_path.glob("crash-*") if path.suffix != ".json"]
    assert (code, artifacts) == (1, [expected])


def test_reduce_cli_preserves_json_fields(mocker: MockerFixture, tmp_path: Path) -> None:
    source = json.dumps({"html": "<div><p>x</p><aside>noise</aside></div>", "css": "p{color:red;margin:1px;}"})

    def check(text: str) -> str | None:
        payload = json.loads(text)
        html, css = payload["html"], payload["css"]
        return (
            "retained"
            if (
                parse_fragment(html).serialize(inner=True) == html
                and "x" in html
                and css.startswith("p{")
                and serialize(parse_stylesheet(css)) == css
                and "margin:1px;" in css
            )
            else None
        )

    mocker.patch.dict(
        ORACLES,
        {
            "probe": Oracle(
                check,
                lambda _rng: source,
                lambda: [source],
                lambda: {"control": True},
                Floor(1, 1),
                fields=("html", "css"),
                syntax="css",
            )
        },
        clear=True,
    )
    code = main(["--minutes", "0", "--crash-dir", str(tmp_path)])
    artifacts = [json.loads(path.read_text()) for path in tmp_path.glob("crash-*") if path.suffix != ".json"]
    assert (code, artifacts) == (1, [{"html": "<div><p>x</p></div>", "css": "p{margin:1px;}"}])


def test_reduce_cli_caps_comparison_calls(mocker: MockerFixture, tmp_path: Path) -> None:
    source = "z" * 2000
    calls = 0

    def check(text: str) -> str | None:
        nonlocal calls
        calls += 1
        return "retained" if text == source else None

    mocker.patch.dict(
        ORACLES,
        {"probe": Oracle(check, lambda _rng: source, lambda: [source], lambda: {"control": True}, Floor(1, 1))},
        clear=True,
    )
    code = main(["--minutes", "0", "--crash-dir", str(tmp_path)])
    artifacts = [path.read_text() for path in tmp_path.glob("crash-*") if path.suffix != ".json"]
    assert (code, artifacts, calls) == (1, [source], 601)
