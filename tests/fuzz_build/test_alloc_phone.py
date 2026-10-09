from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

import turbohtml
from turbohtml.clean import LinkDetector, Linker, Linkify, PhoneFormat, PhoneNumber, PhoneNumbers

if TYPE_CHECKING:
    from collections.abc import Callable

# numbers from three regions, an extension, an email and a URL, so a linkify walk splits the run into many nodes
_TEXT: Final = (
    "Call +1 650-253-0000 or (650) 253-0000 ext. 123, London +44 20 7946 0958, Berlin 030 123456, "
    "mail a@example.com or see https://example.com/x"
)
_PHONES: Final = PhoneNumbers(regions=("US", "GB", "DE"))
_LINKER: Final = Linker(Linkify(phones=_PHONES, parse_email=True))
_DETECTOR: Final = LinkDetector(phones=_PHONES)
_NUMBER: Final = PhoneNumber.parse("+44 20 7946 0958")


def _fragment() -> turbohtml.Node:
    # a fresh tree per run; serializing copies the parsed text out of the input, so the sweep fails only the walk
    root = turbohtml.parse_fragment(f"<p>{_TEXT}</p>")
    root.serialize()
    return root


@pytest.mark.parametrize(
    ("call", "setup"),
    [
        pytest.param(_LINKER.linkify_node, _fragment, id="linkify-node"),
        pytest.param(lambda _: _DETECTOR.find(_TEXT), lambda: None, id="find"),
        pytest.param(lambda _: PhoneNumber.parse("(650) 253-0000", regions=("US",)), lambda: None, id="parse"),
        pytest.param(lambda _: [_NUMBER.format(style) for style in PhoneFormat], lambda: None, id="format"),
    ],
)
def test_phone_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], call: Callable[[object], object], setup: Callable[[], object]
) -> None:
    call(setup())  # fill the lazily built region tables first, so the sweep counts only the call's own allocations
    assert set(alloc_sweep(call, setup)) == {"MemoryError"}
