from __future__ import annotations

from typing import Final

import pytest

from turbohtml.extract import extract_links


@pytest.mark.parametrize("depth", [0, 16, 128], ids=["ordinary", "nested", "beyond-dns-length"])
@pytest.mark.parametrize(
    ("base", "host", "external"),
    [
        pytest.param("example.co.uk", "example.co.uk", False, id="normal-shared"),
        pytest.param("example.co.uk", "other.co.uk", True, id="normal-distinct"),
        pytest.param("a.github.io", "b.github.io", True, id="private-distinct"),
        pytest.param("www.ck", "www.ck", False, id="exception-shared"),
        pytest.param("a.ck", "b.ck", True, id="wildcard-distinct"),
        pytest.param("example.invalid", "s.example.invalid", True, id="unknown-host-compared-whole"),
        pytest.param("münchen.de", "xn--mnchen-3ya.de", False, id="idna-shared"),
        pytest.param(
            "a.foo.001.test.code-builder-stg.platform.salesforce.com",
            "b.foo.001.test.code-builder-stg.platform.salesforce.com",
            True,
            id="deepest-wildcard-distinct",
        ),
    ],
)
def test_external_links_keep_public_suffix_boundary(base: str, host: str, *, depth: int, external: bool) -> None:
    href: Final = f"https://{'s.' * depth}{host}/x"
    assert extract_links(f'<a href="{href}">x</a>', f"https://{base}/", external_only=True) == (
        {href} if external else set()
    )
