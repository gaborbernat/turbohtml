from __future__ import annotations

from typing import Final

import pytest

from turbohtml.extract import clean_url, extract_links, normalize_url


@pytest.mark.parametrize(
    "host",
    [
        pytest.param(f"a%{code:02X}b.example", id=f"encoded-{code:02x}")
        for code in (*range(0x21), 0x23, 0x25, 0x2F, 0x3A, 0x3C, 0x3E, 0x3F, 0x40, 0x5B, 0x5C, 0x5D, 0x5E, 0x7C, 0x7F)
    ]
    + [
        pytest.param("\uff05\uff10\uff10", id="mapped-null-escape"),
        pytest.param("\uff05\uff14\uff11", id="mapped-letter-escape"),
        pytest.param("a\uff03b.example", id="mapped-fragment-delimiter"),
        pytest.param("a\uff1ab.example", id="mapped-port-delimiter"),
        pytest.param("a\uff20b.example", id="mapped-userinfo-delimiter"),
    ],
)
def test_normalize_rejects_forbidden_domain(host: str) -> None:
    with pytest.raises(ValueError, match="host contains a forbidden domain code point"):
        normalize_url(f"http://{host}/")


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("//\uff05\uff10\uff10", id="mapped-null"),
        pytest.param("http://o%23", id="fragment"),
        pytest.param("http://o%3F", id="query"),
        pytest.param("//\uff05\uff14\uff11", id="mapped-escape"),
        pytest.param("file://%3A", id="port"),
        pytest.param("//%09t", id="tab"),
    ],
)
def test_normalize_rejects_saved_reparse_findings(source: str) -> None:
    with pytest.raises(ValueError, match="host contains a forbidden domain code point"):
        normalize_url(source)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("http://good%2eexample/", "http://good.example/", id="decoded-dot"),
        pytest.param("http://%41.example/", "http://a.example/", id="decoded-letter"),
        pytest.param("http://caf%C3%A9.example/", "http://xn--caf-dma.example/", id="decoded-unicode"),
        pytest.param("http://a\u0085b.example/", "http://a\u0085b.example/", id="retained-c1-fallback"),
        pytest.param("http://a\u2028b.example/", "http://a\u2028b.example/", id="retained-disallowed-fallback"),
        pytest.param("file:///", "file:///", id="empty-file-host"),
        pytest.param("http://[::1]/", "http://[::1]/", id="ipv6"),
    ],
)
def test_normalize_host_valid_and_fallback_forms(source: str, expected: str) -> None:
    normalized: Final = normalize_url(source)
    assert (normalized, normalize_url(normalized)) == (expected, expected)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("http://a%23b.example/", id="decoded-fragment"),
        pytest.param("http://a\uff05\uff14\uff11.example/", id="mapped-escape"),
    ],
)
def test_clean_rejects_forbidden_domain(source: str) -> None:
    assert clean_url(source) is None


def test_external_links_reject_forbidden_base_domain() -> None:
    with pytest.raises(ValueError, match="host contains a forbidden domain code point"):
        extract_links("<a href='https://valid.example/'>link</a>", "http://a%23b.example/", external_only=True)
