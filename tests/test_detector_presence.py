from __future__ import annotations

import pytest

from turbohtml.linkify import Detector


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("see http://example.com", True, id="scheme-url"),
        pytest.param("bare example.com here", True, id="bare-domain"),
        pytest.param("mail bob@example.com", True, id="email"),
        pytest.param("nothing here at all", False, id="no-link"),
        pytest.param("", False, id="empty"),
    ],
)
def test_has_link(text: str, expected: bool) -> None:
    assert Detector().has_link(text) is expected


def test_has_link_respects_configuration() -> None:
    detector = Detector(emails=False, bare_domains=False)
    assert detector.has_link("write bob@example.com or visit example.com") is False
    assert detector.has_link("but https://example.com still counts") is True
