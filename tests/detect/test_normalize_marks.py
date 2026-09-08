from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING, Final

import pytest

from turbohtml.detect import normalize

if TYPE_CHECKING:
    from turbohtml.detect import NormalizationForm


@pytest.mark.parametrize("form", ["NFC", "NFD", "NFKC", "NFKD"])
@pytest.mark.parametrize("size", [1, 31, 32, 33, 1_000], ids=["single", "31-marks", "32-marks", "33-marks", "long"])
@pytest.mark.parametrize("starter", [pytest.param("", id="leading"), pytest.param("a", id="starter")])
def test_normalize_reorders_long_runs(form: NormalizationForm, size: int, starter: str) -> None:
    text: Final[str] = starter + "\u0315" * size + "\u0300\u0301" * size + "b" + "\u0323\u0300" * size
    assert normalize(form, text) == unicodedata.normalize(form, text)
