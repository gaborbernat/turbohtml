from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Final

import pytest

import turbohtml

if TYPE_CHECKING:
    from collections.abc import Callable

    from turbohtml import ParseError

# Each seed opens with the error it targets, so recording that error is the error list's first allocation: a control
# and a noncharacter for the preprocessing scan (in a wide and a one-byte str, which it reads on separate paths), a
# duplicate attribute and a NUL reference for the tokenizer, and a second doctype and a self-closed div for the tree
# builder.
_SEEDS: Final = {
    "control-wide": "\x01\ufdd0<!DOCTYPE html>",
    "control-one-byte": "\x01\xa0<!DOCTYPE html>",
    "duplicate-attribute": "<!DOCTYPE html><p a=1 a=2>",
    "nul-reference": "<!DOCTYPE html>&#0;",
    "second-doctype": "<!DOCTYPE html><!DOCTYPE x>",
    "self-closed-div": "<!DOCTYPE html><div/>",
}


def _errors(seed: str) -> list[ParseError]:
    return turbohtml.parse(seed).errors


def _strict(seed: str) -> None:
    with contextlib.suppress(turbohtml.HTMLParseError):
        turbohtml.parse(seed, strict=True)


def _streamed(seed: str) -> list[ParseError]:
    parser = turbohtml.IncrementalParser()
    parser.feed(seed[:4])
    parser.feed(seed[4:])
    return parser.close().errors


@pytest.mark.parametrize("seed", [pytest.param(seed, id=name) for name, seed in _SEEDS.items()])
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(_errors, id="errors"),
        pytest.param(_strict, id="strict"),
        pytest.param(_streamed, id="incremental"),
    ],
)
def test_parse_error_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], call: Callable[[str], object], seed: str
) -> None:
    assert set(alloc_sweep(lambda _: call(seed))) == {"MemoryError"}


def test_xml_parse_error_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]],
) -> None:
    def parse_malformed(_: object) -> None:
        with contextlib.suppress(turbohtml.HTMLParseError):
            turbohtml.parse_xml("<a><b></a>")

    assert set(alloc_sweep(parse_malformed)) == {"MemoryError"}


def test_parse_error_read_retries_after_allocation_failure(alloc_sweep: Callable[..., list[str]]) -> None:
    # the first read of Document.errors merges the preprocessing errors; a read that failed to allocate leaves them
    # unmerged, so the next read returns the complete list
    seed = _SEEDS["control-wide"]
    expected = [(error.code, error.line, error.col) for error in turbohtml.parse(seed).errors]
    documents: list[turbohtml.Document] = []

    def setup() -> turbohtml.Document:
        documents.append(turbohtml.parse(seed))
        return documents[-1]

    alloc_sweep(lambda document: document.errors, setup)
    assert {tuple((error.code, error.line, error.col) for error in document.errors) for document in documents} == {
        tuple(expected)
    }
