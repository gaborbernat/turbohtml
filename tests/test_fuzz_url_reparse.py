from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fuzz.round_trip_oracles import ORACLES, OutOfScopeError, main, url_reparse_check

from turbohtml.extract import normalize_url

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("HTTPS://Example.test/a?b=2&a=1#f", "https://example.test/a?a=1&b=2#f", id="canonical-components"),
        pytest.param("https:a", "https:a", id="special-without-authority"),
        pytest.param("file:///tmp/x", "file:///tmp/x", id="empty-authority"),
        pytest.param("file:/tmp/x", "file:///tmp/x", id="file-without-authority"),
        pytest.param("//host/a?q=1#f", "//host/a?q=1#f", id="scheme-relative"),
        pytest.param("a/b?x=1#f", "a/b?x=1#f", id="relative"),
        pytest.param("mailto:a@b.test", "mailto:a@b.test", id="opaque"),
        pytest.param("http://example.test/?#", "http://example.test/", id="empty-delimiters"),
        pytest.param("https://example.test/#?", "https://example.test/#?", id="query-mark-in-fragment"),
    ],
)
def test_url_reparse_public_components(source: str, expected: str) -> None:
    assert (normalize_url(source), url_reparse_check(source)) == (expected, None)


@pytest.mark.parametrize(
    "normalized",
    [
        pytest.param("https://example.test/?", id="bare-query"),
        pytest.param("https://example.test/#", id="bare-fragment"),
        pytest.param("file:///x?#", id="all-delimiters"),
    ],
)
def test_url_reparse_keeps_optional_delimiters(normalized: str) -> None:
    assert url_reparse_check("raw", lambda _text: normalized) is None


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("https://[broken/", id="target-rejection"),
        pytest.param("https://[bad]/", id="reference-bracket-rejection"),
    ],
)
def test_url_reparse_rejects_unsupported_domain(source: str) -> None:
    with pytest.raises(OutOfScopeError):
        url_reparse_check(source)


@pytest.mark.parametrize(
    "output",
    [
        pytest.param("HTTPS://example.test/", id="stable-upper-scheme"),
        pytest.param(" https://example.test/", id="leading-space"),
        pytest.param("https://exam\tple.test/", id="embedded-tab"),
    ],
)
def test_url_reparse_detects_noncanonical_split(output: str) -> None:
    assert (result := url_reparse_check("raw", lambda _text: output)) is not None
    assert result.startswith("split/recompose changes normalized URL")


def test_url_reparse_detects_changed_second_result() -> None:
    assert (
        result := url_reparse_check(
            "raw", lambda text: "https://example.test/" if text == "raw" else "https://changed.test/"
        )
    ) is not None
    assert result.startswith("reparse changes normalized URL")


def test_url_reparse_detects_rejection_of_recomposed_output() -> None:
    def reject(text: str) -> str:
        if text == "raw":
            return "https://example.test/"
        msg = "rejected"
        raise ValueError(msg)

    assert url_reparse_check("raw", reject) == "rejects recomposed output"


def test_url_reparse_controls_discriminate() -> None:
    assert ORACLES["url-split-reparse"].controls() == {
        "stable uppercased scheme": True,
        "changes after recomposition": True,
        "rejects recomposed output": True,
    }


def test_url_reparse_cli_is_registered(
    mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seeds = tmp_path / "tools/fuzz-data/wpt/url/resources/urltestdata.json"
    seeds.parent.mkdir(parents=True)
    seeds.write_text('[{"input": "HTTP://Example.COM:80/"}]', encoding="utf-8")
    corpus = tmp_path / "tools/fuzz/corpus/url"
    corpus.mkdir(parents=True)
    (corpus / "url.txt").write_text("https://seed.example/", encoding="utf-8")
    mocker.patch("fuzz.round_trip_oracles._ROOT", tmp_path)
    assert (
        main(["--oracle", "url-split-reparse", "--minutes", "0", "--crash-dir", str(tmp_path)]),
        capsys.readouterr().out.splitlines()[-1],
    ) == (0, f"0 finding(s) written to {tmp_path}")
