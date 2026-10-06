from __future__ import annotations

import json
import random
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.parser_byte_oracles import (
    UnsupportedParserCaseError,
    parser_bytes_check,
    parser_bytes_controls,
    parser_bytes_generate,
    parser_bytes_seeds,
)
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main

from turbohtml import IncrementalParser, parse

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("variant", "raw", "label", "expected", "encoding"),
    [
        pytest.param(
            "utf8",
            b"<p>caf\xc3\xa9 \xe6\x97\xa5\xe6\x9c\xac\xf0\x9f\x98\x80</p>",
            "utf-8",
            "café 日本😀",
            "UTF-8",
            id="utf8",
        ),
        pytest.param("shift-jis", b"<p>\x93\xfa\x96{\x8c\xea</p>", "shift_jis", "日本語", "Shift_JIS", id="shift-jis"),
        pytest.param(
            "iso-2022-jp", b"<p>\x1b$BF|K\\8l\x1b(B</p>", "iso-2022-jp", "日本語", "ISO-2022-JP", id="iso-2022-jp"
        ),
        pytest.param("windows1252", b"<p>caf\xe9 \x80</p>", "windows-1252", "café €", "windows-1252", id="windows1252"),
        pytest.param("utf8-bom", b"\xef\xbb\xbf<p>\xc3\xa9</p>", "windows-1252", "é", "UTF-8", id="utf8-bom"),
        pytest.param(
            "utf16le-bom",
            b"\xff\xfe<\x00p\x00>\x00\xe9\x00<\x00/\x00p\x00>\x00",
            "windows-1252",
            "é",
            "UTF-16LE",
            id="utf16le-bom",
        ),
        pytest.param(
            "utf16be-bom",
            b"\xfe\xff\x00<\x00p\x00>\x00\xe9\x00<\x00/\x00p\x00>",
            "utf-8",
            "é",
            "UTF-16BE",
            id="utf16be-bom",
        ),
    ],
)
def test_parser_byte_oracle_pins_text_and_canonical_label(
    variant: str, raw: bytes, label: str, expected: str, encoding: str
) -> None:
    document: Final = parse(raw, encoding=label)
    outcomes: Final = [(document.text, document.encoding)]
    for width in (1, 2, 3, 4, 5, len(raw)):
        parser = IncrementalParser(encoding=label)
        parser.feed(b"")
        for start in range(0, len(raw), width):
            parser.feed(raw[start : start + width])
            parser.feed(b"")
        result = parser.close()
        outcomes.append((result.text, result.encoding))
    assert (outcomes, parser_bytes_check(f"{variant}:g")) == ([(expected, encoding)] * 7, None)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("utf8", id="missing-separator"),
        pytest.param("unknown:g", id="unknown-fixture"),
        pytest.param("utf8:", id="empty-prefix"),
        pytest.param("utf8:é", id="non-ascii-prefix"),
        pytest.param("utf8:g<p>", id="markup-prefix"),
        pytest.param("utf8:g" + "1" * 16, id="overlong-prefix"),
    ],
)
def test_parser_byte_oracle_rejects_unsupported_grammar(source: str) -> None:
    with pytest.raises(UnsupportedParserCaseError):
        parser_bytes_check(source)
    with pytest.raises(OutOfScopeError):
        ORACLES["parser-bytes"].check(source)


@pytest.mark.parametrize(
    ("one_shot", "stream", "expected"),
    [
        pytest.param(
            lambda _data, _label: ("", "UTF-8"),
            None,
            "one-shot parser differs from fixed text or label",
            id="wrong-first-text",
        ),
        pytest.param(
            lambda _data, _label: ("g:café 日本😀", None),
            None,
            "one-shot parser differs from fixed text or label",
            id="wrong-first-label",
        ),
        pytest.param(
            None,
            lambda _data, _label, _width: ("", "UTF-8"),
            "streaming parser differs from fixed text or label",
            id="wrong-stream-text",
        ),
        pytest.param(
            None,
            lambda _data, _label, _width: ("g:café 日本😀", None),
            "streaming parser differs from fixed text or label",
            id="wrong-stream-label",
        ),
        pytest.param(
            lambda _data, _label: ("", None),
            lambda _data, _label, _width: ("", None),
            "one-shot parser differs from fixed text or label",
            id="shared-wrong-agreement",
        ),
    ],
)
def test_parser_byte_oracle_discriminates_wrong_results(
    one_shot: Callable[[bytes, str], tuple[str, str | None]] | None,
    stream: Callable[[bytes, str, int], tuple[str, str | None]] | None,
    expected: str,
) -> None:
    assert parser_bytes_check("utf8:g", one_shot, stream) == expected


def test_parser_byte_registry_generated_cases_and_controls() -> None:
    rng: Final = random.SystemRandom()
    generated: Final = [parser_bytes_generate(rng) for _ in range(100)]
    seeds: Final = parser_bytes_seeds()
    assert (
        len(seeds),
        all(parser_bytes_check(case) is None for case in [*seeds, *generated]),
        parser_bytes_controls(),
    ) == (
        210,
        True,
        {
            "wrong one-shot text": True,
            "wrong one-shot label": True,
            "wrong streaming text": True,
            "wrong streaming label": True,
            "shared wrong result": True,
        },
    )


def test_parser_byte_cli_compares_seed_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status: Final = main(["--oracle", "parser-bytes", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, list(tmp_path.glob("crash-*")), "210" in capsys.readouterr().out) == (0, [], True)


def test_parser_byte_cli_reports_valid_fixture_rejection(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["parser-bytes"],
        check=partial(parser_bytes_check, one_shot=_reject_fixture),
        seeds=lambda: ["utf8:g"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"parser-bytes": oracle}, clear=True)
    status: Final = main(["--oracle", "parser-bytes", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (status, len(findings), payload["detail"], payload["hits"]) == (1, 1, "raised ValueError", 1)


def _reject_fixture(_data: bytes, _label: str) -> tuple[str, str | None]:
    message: Final = "rejected valid bytes"
    raise ValueError(message)


def test_parser_byte_cli_rejects_vacuous_run(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(
        ORACLES,
        {"parser-bytes": replace(ORACLES["parser-bytes"], seeds=lambda: ["unknown:g"], floor=Floor(1, 1))},
        clear=True,
    )
    assert main(["--oracle", "parser-bytes", "--minutes", "0", "--crash-dir", str(tmp_path)]) == 2
