from __future__ import annotations

import json
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, encoding_decode_check, encoding_stream_check, main

from turbohtml import parse
from turbohtml.detect import EncodingDetector, EncodingMatch, detect

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("case", "data", "label", "decoded"),
    [
        pytest.param("utf-8-bom\ncafé", b"\xef\xbb\xbf<p>caf\xc3\xa9</p>", "UTF-8-SIG", "<p>café</p>", id="utf8-bom"),
        pytest.param(
            "utf-16le-bom\ncafé",
            b"\xff\xfe" + "<p>café</p>".encode("utf-16-le"),
            "UTF-16LE",
            "\ufeff<p>café</p>",
            id="utf16le-bom",
        ),
        pytest.param(
            "utf-16be-bom\ncafé",
            b"\xfe\xff" + "<p>café</p>".encode("utf-16-be"),
            "UTF-16BE",
            "\ufeff<p>café</p>",
            id="utf16be-bom",
        ),
        pytest.param(
            "utf-8-meta\ncafé",
            b"<meta charset=utf-8><p>caf\xc3\xa9</p>",
            "UTF-8",
            "<meta charset=utf-8><p>café</p>",
            id="utf8-meta",
        ),
        pytest.param(
            "windows-1252-meta\ncafé",
            b"<meta charset=windows-1252><p>caf\xe9</p>",
            "windows-1252",
            "<meta charset=windows-1252><p>café</p>",
            id="windows1252-meta",
        ),
    ],
)
def test_encoding_invariants_pin_public_outputs(case: str, data: bytes, label: str, decoded: str) -> None:
    match: Final = detect(data)
    assert match.codec is not None
    assert (
        match.encoding,
        data.decode(match.codec),
        parse(data).text,
        encoding_stream_check(case),
        encoding_decode_check(case),
    ) == (label, decoded, "café", None, None)


@pytest.mark.parametrize(
    "check",
    [
        pytest.param(encoding_stream_check, id="stream"),
        pytest.param(encoding_decode_check, id="decode"),
    ],
)
@pytest.mark.parametrize(
    "case",
    [
        pytest.param("utf-8-bom", id="missing-separator"),
        pytest.param("unknown\ntext", id="unknown-fixture"),
        pytest.param("empty\ntext", id="nonempty-sentinel"),
        pytest.param("utf-8-meta\n" + "a" * 257, id="bounded-size"),
        pytest.param("utf-8-meta\n\x00", id="html-nul-preprocessing"),
        pytest.param("utf-8-meta\n<p>", id="markup"),
        pytest.param("utf-8-meta\n&copy;", id="entity"),
        pytest.param("windows-1252-meta\n𐐀", id="unrepresentable"),
    ],
)
def test_encoding_invariants_reject_unsupported_cases(check: Callable[[str], str | None], case: str) -> None:
    with pytest.raises(OutOfScopeError):
        check(case)


def test_encoding_stream_empty_sentinel() -> None:
    detector: Final = EncodingDetector()
    detector.feed(b"")
    assert (detect(b""), detector.close(), encoding_stream_check("empty\n")) == (
        EncodingMatch(None, 0.0, None),
        EncodingMatch(None, 0.0, None),
        None,
    )


def test_encoding_decode_empty_sentinel_is_out_of_scope() -> None:
    with pytest.raises(OutOfScopeError):
        encoding_decode_check("empty\n")


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        pytest.param(
            lambda case: encoding_stream_check(case, one_shot=lambda _data: EncodingMatch(None, 0.0, None)),
            "one-shot detection differs from expected match",
            id="wrong-one-shot",
        ),
        pytest.param(
            lambda case: encoding_stream_check(case, stream=lambda _data, _width: EncodingMatch(None, 0.0, None)),
            "chunked detection differs from expected match",
            id="wrong-stream",
        ),
        pytest.param(
            lambda case: encoding_decode_check(case, detect_bytes=lambda _data: EncodingMatch(None, 0.0, None)),
            "detection differs from expected match",
            id="wrong-detection",
        ),
        pytest.param(
            lambda case: encoding_decode_check(case, decode=lambda _data, _codec: ""),
            "detected codec differs from expected text",
            id="wrong-codec",
        ),
        pytest.param(
            lambda case: encoding_decode_check(case, parse_text=lambda _data: None),
            "byte parse differs from expected text",
            id="missing-parse-text",
        ),
    ],
)
def test_encoding_invariants_discriminate_failures(check: Callable[[str], str | None], expected: str) -> None:
    assert check("utf-8-meta\ncafé") == expected


@pytest.mark.parametrize(
    "name", [pytest.param("encoding-stream", id="stream"), pytest.param("encoding-decode", id="decode")]
)
def test_encoding_registry_controls_seeds_and_floor(name: str) -> None:
    oracle: Final = ORACLES[name]
    assert (
        oracle.check("utf-8-meta\ncafé"),
        all(oracle.controls().values()),
        oracle.floor.count,
        len(oracle.seeds()),
    ) == (None, True, 100, 156)


def test_encoding_cli_replays_seed_floor(tmp_path: Path) -> None:
    assert (
        main([
            "--oracle",
            "encoding-stream",
            "--oracle",
            "encoding-decode",
            "--minutes",
            "0",
            "--crash-dir",
            str(tmp_path),
        ])
        == 0
    )


def test_encoding_cli_emits_wrong_detection(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["encoding-stream"],
        check=partial(encoding_stream_check, one_shot=lambda _data: EncodingMatch(None, 0.0, None)),
        seeds=lambda: ["utf-8-meta\ncafé"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"encoding-stream": oracle}, clear=True)
    status: Final = main(["--oracle", "encoding-stream", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (status, [json.loads(path.read_text(encoding="utf-8")) for path in tmp_path.glob("crash-*.json")]) == (
        1,
        [
            {
                "oracle": "encoding-stream",
                "detail": "one-shot detection differs from expected match",
                "hits": 1,
                "rng_seed": 0,
            }
        ],
    )
