from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Element, Html, Indent, Minify, Text


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param('a<&>"', id="escaping"),
        pytest.param("\x7f\u0080\u07ff", id="two-byte-boundaries"),
        pytest.param("\u0800\ud7ff\ue000\uffff", id="three-byte-boundaries"),
        pytest.param("\U00010000\U0010ffff", id="four-byte-boundaries"),
    ],
)
@pytest.mark.parametrize("encoding", ["utf-8", "UTF8", "utf-16-le"])
@pytest.mark.parametrize(
    "options",
    [
        pytest.param(Html(), id="compact"),
        pytest.param(Html(layout=Indent("é😀")), id="indent"),
        pytest.param(Html(layout=Minify()), id="minify"),
        pytest.param(Html(xml=True), id="xml"),
    ],
)
@pytest.mark.parametrize("inner", [False, True], ids=["outer", "inner"])
def test_encode_unicode(text: str, encoding: str, options: Html, *, inner: bool) -> None:
    root: Final = Element("p", children=[Text(text)])
    assert root.encode(encoding, options, inner=inner) == root.serialize(options, inner=inner).encode(encoding)


@pytest.mark.parametrize("text", ["\ud800", "a\udfff", "é😀\ud800\udfff"])
@pytest.mark.parametrize("inner", [False, True], ids=["outer", "inner"])
def test_encode_surrogate_error(text: str, *, inner: bool) -> None:
    root: Final = Element("p", children=[Text(text)])
    with pytest.raises(UnicodeEncodeError) as expected:
        root.serialize(inner=inner).encode()
    with pytest.raises(UnicodeEncodeError) as actual:
        root.encode(inner=inner)
    assert actual.value.args == expected.value.args
