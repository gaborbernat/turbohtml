from __future__ import annotations

import pytest
from fuzz.atheris_header import HEADER_SIZE, SEED_HEADER, Header, feed_chunks, split_header


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param(Header(7, 5, 3).encode() + b"<p>", (Header(7, 5, 3), b"<p>"), id="fields-then-payload"),
        pytest.param(
            Header(0, 300, 40).encode() + b"<p>", (Header(0, 300 % 115, 40 % 17), b"<p>"), id="modulo-by-size"
        ),
        pytest.param(Header(0, 0, 0).encode(), (Header(0, 0, 1), b""), id="zero-chunk-reads-as-one"),
        pytest.param(b"\x01\x02", (Header(0x0102, 0, 1), b""), id="short-input-reads-fewer-bytes"),
    ],
)
def test_atheris_header_split(data: bytes, expected: tuple[Header, bytes]) -> None:
    assert split_header(data) == expected


def test_atheris_header_seed_layout() -> None:
    assert (12, bytes(8) + (256).to_bytes(4, "big")) == (HEADER_SIZE, SEED_HEADER)


@pytest.mark.parametrize(
    ("data", "max_chunk", "expected"),
    [
        pytest.param(b"", 4, [b"", b"", b""], id="empty"),
        pytest.param(b"abcde", 2, [b"", b"ab", b"", b"cd", b"", b"e", b""], id="pieces"),
        pytest.param(
            b"a" * 150, 1, [b"", *(piece for _ in range(50) for piece in (b"a", b"")), b"a" * 100, b""], id="cap"
        ),
    ],
)
def test_atheris_header_feed_chunks_bytes(data: bytes, max_chunk: int, expected: list[bytes]) -> None:
    fed: list[bytes] = []
    feed_chunks(fed.append, data, max_chunk)
    assert fed == expected


def test_atheris_header_feed_chunks_text() -> None:
    fed: list[str] = []
    feed_chunks(fed.append, "水😀x", 1)
    assert fed == ["", "水", "", "😀", "", "x", ""]
