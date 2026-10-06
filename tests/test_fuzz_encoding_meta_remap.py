from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from fuzz.round_trip_oracles import encoding_decode_check, encoding_stream_check

from turbohtml import parse
from turbohtml.detect import EncodingMatch, detect

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize("declared", ["utf-16", "utf-16le", "utf-16be"])
def test_encoding_meta_remap_preserves_public_text(declared: str) -> None:
    text: Final = "café €中文𐐀"
    markup: Final = f"<meta charset={declared}><p>{text}</p>"
    data: Final = markup.encode("utf-8")
    case: Final = f"{declared}-meta-remap\n{text}"
    match: Final = detect(data)
    assert match.codec is not None
    assert (
        match.encoding,
        match.codec,
        data.decode(match.codec),
        parse(data).text,
        encoding_stream_check(case),
        encoding_decode_check(case),
    ) == ("UTF-8", "whatwg-utf-8", markup, text, None, None)


@pytest.mark.parametrize("declared", ["utf-16", "utf-16le", "utf-16be"])
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
            id="missing-decoded-text",
        ),
        pytest.param(
            lambda case: encoding_decode_check(case, parse_text=lambda _data: ""),
            "byte parse differs from expected text",
            id="missing-parsed-text",
        ),
    ],
)
def test_encoding_meta_remap_discriminates_wrong_targets(
    declared: str, check: Callable[[str], str | None], expected: str
) -> None:
    assert check(f"{declared}-meta-remap\ncafé") == expected
