from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING, Final

import pytest

from turbohtml.detect import normalize

if TYPE_CHECKING:
    from turbohtml.detect import NormalizationForm


@pytest.mark.parametrize("form", [pytest.param(form, id=form) for form in ("NFC", "NFD", "NFKC", "NFKD")])
@pytest.mark.parametrize(
    "size",
    [
        pytest.param(1, id="single"),
        pytest.param(31, id="31-marks"),
        pytest.param(32, id="32-marks"),
        pytest.param(33, id="33-marks"),
        pytest.param(1_000, id="long"),
    ],
)
@pytest.mark.parametrize("starter", [pytest.param("", id="leading"), pytest.param("a", id="starter")])
def test_normalize_reorders_long_runs(form: NormalizationForm, size: int, starter: str) -> None:
    text: Final[str] = starter + "\u0315" * size + "\u0300\u0301" * size + "b" + "\u0323\u0300" * size
    assert normalize(form, text) == unicodedata.normalize(form, text)
