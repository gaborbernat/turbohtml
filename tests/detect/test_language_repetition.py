from __future__ import annotations

import pytest

from turbohtml.detect import LanguageMatch, detect_language


@pytest.mark.parametrize(
    "repeats",
    [pytest.param(1, id="sentence"), pytest.param(100, id="page"), pytest.param(10_000, id="long-prose")],
)
def test_language_detection_of_repeated_prose(repeats: int) -> None:
    assert detect_language(
        "There is no reason not to learn a new language every single year of your life. " * repeats
    ) == LanguageMatch("eng", 1.0, "Latin", "English")
