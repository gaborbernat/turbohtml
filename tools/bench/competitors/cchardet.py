"""cchardet via faust-cchardet: the C uchardet binding (the original cchardet stops building at Python 3.10)."""

from __future__ import annotations

from typing import Final

import cchardet

REQUIREMENTS = ("faust-cchardet>=2.1.19",)


def encoding(data: bytes) -> None:
    """Detect a byte stream's character encoding with cchardet's uchardet engine."""
    cchardet.detect(data)


def _encoding_stream(data: bytes) -> None:
    detector: Final = cchardet.UniversalDetector()
    detector.feed(data)
    detector.close()


OPERATIONS = {
    "encoding-result-stream": (_encoding_stream, "faust-cchardet"),
    "encoding": (encoding, "faust-cchardet"),
    "encoding-result": (encoding, "faust-cchardet"),
}
