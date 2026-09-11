from __future__ import annotations

from typing import Final

import pytest

from turbohtml import tokenize


@pytest.mark.parametrize("count", [0, 1, 10, 100], ids=["empty", "one", "ten", "hundred"])
def test_token_attrs_order(count: int) -> None:
    expected: Final = [(f"a{index}", str(index)) for index in range(count)]
    (token,) = tokenize(f"<p {' '.join(f'{name}={value}' for name, value in expected)}>")
    assert token.attrs == expected


@pytest.mark.parametrize("document", ["<p>", "<p a=1 b=2>"], ids=["empty", "populated"])
def test_token_attrs_returns_fresh_list(document: str) -> None:
    (token,) = tokenize(document)
    expected: Final = token.attrs
    attrs: Final = token.attrs
    assert attrs is not None
    attrs[:] = [("replacement", "changed")]
    assert token.attrs == expected
