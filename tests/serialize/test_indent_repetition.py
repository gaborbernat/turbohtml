from __future__ import annotations

from typing import Final

import pytest

from turbohtml import Html, Indent, parse_fragment


@pytest.mark.parametrize(
    "unit",
    [
        pytest.param("", id="empty"),
        pytest.param(" ", id="space"),
        pytest.param("\t ", id="mixed"),
        pytest.param("é😀", id="unicode"),
        pytest.param("\t " * 1000, id="chunk-boundary"),
    ],
)
@pytest.mark.parametrize("inner", [False, True], ids=["outer", "inner"])
@pytest.mark.parametrize("method", ["serialize", "encode", "stream"])
def test_indent_repetition(unit: str, *, inner: bool, method: str) -> None:
    root: Final = parse_fragment("<section><p>x</p></section>")
    options: Final = Html(layout=Indent(unit))
    expected: Final = (
        f"<section>\n{unit}<p>\n{unit * 2}x\n{unit}</p>\n</section>"
        if inner
        else f"<div>\n{unit}<section>\n{unit * 2}<p>\n{unit * 3}x\n{unit * 2}</p>\n{unit}</section>\n</div>"
    )
    if method == "stream":
        output: Final = "".join(root.serialize_iter(options, inner=inner))
    elif method == "encode":
        output = root.encode(options=options, inner=inner).decode()
    else:
        output = root.serialize(options, inner=inner)
    assert output == expected
