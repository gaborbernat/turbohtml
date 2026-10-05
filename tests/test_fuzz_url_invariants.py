from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

import pytest
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, clean_url_check, main, normalize_url_check

from turbohtml.extract import clean_url, normalize_url

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            "HTTP://Example.COM:80/a/../b?utm_source=x&z=2&a=1", "http://example.com/b?a=1&z=2", id="canonical"
        ),
        pytest.param("https://bücher.example/café", "https://xn--bcher-kva.example/caf%C3%A9", id="unicode"),
    ],
)
def test_normalize_url_invariant_pins_output(source: str, expected: str) -> None:
    assert (normalize_url(source), normalize_url(expected), normalize_url_check(source)) == (expected, expected, None)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("HTTP://Example.COM:80/?utm_source=x", "http://example.com/", id="canonical"),
        pytest.param(" http://test.org/?a=1&amp;b=2 ", "http://test.org/?a=1&b=2", id="markup-damage"),
    ],
)
def test_clean_url_invariant_pins_output(source: str, expected: str) -> None:
    assert (clean_url(source), clean_url(expected), clean_url_check(source)) == (expected, expected, None)


@pytest.mark.parametrize(
    ("check", "source"),
    [
        pytest.param(normalize_url_check, "http://[", id="malformed-normalization"),
        pytest.param(clean_url_check, "javascript:alert(1)", id="unsupported-cleaning"),
        pytest.param(clean_url_check, "http://[", id="malformed-cleaning"),
    ],
)
def test_url_invariants_count_initial_rejection_as_out_of_scope(
    check: Callable[[str], str | None], source: str
) -> None:
    with pytest.raises(OutOfScopeError):
        check(source)


@pytest.mark.parametrize(
    ("transform", "expected"),
    [
        pytest.param(lambda text: text + "a", "not a fixpoint: end vs letter", id="changed-output"),
        pytest.param(lambda text: "ok" if text == "raw" else None, "rejects its own output", id="none-after-success"),
        pytest.param(
            lambda text: _reject() if text == "ok" else "ok", "rejects its own output", id="error-after-success"
        ),
        pytest.param(lambda _text: _reject(), None, id="error-on-input"),
    ],
)
def test_clean_url_invariant_discriminates_failures(
    transform: Callable[[str], str | None], expected: str | None
) -> None:
    if expected is None:
        with pytest.raises(OutOfScopeError):
            clean_url_check("raw", transform)
    else:
        assert clean_url_check("raw", transform) == expected


def _reject() -> str:
    msg = "rejected"
    raise ValueError(msg)


@pytest.mark.parametrize("name", ["normalize-url-fixpoint", "clean-url-fixpoint"])
def test_url_registry_controls_and_floor(name: str) -> None:
    oracle = ORACLES[name]
    assert (oracle.check("HTTP://Example.COM:80/"), all(oracle.controls().values()), oracle.floor.count) == (
        None,
        True,
        100,
    )


def test_url_registry_seeds_use_wpt_inputs(mocker: MockerFixture, tmp_path: Path) -> None:
    wpt = tmp_path / "tools/fuzz-data/wpt/url/resources/urltestdata.json"
    wpt.parent.mkdir(parents=True)
    wpt.write_text(
        json.dumps(["description", {"input": "HTTP://Example.COM:80/", "href": "ignored"}]), encoding="utf-8"
    )
    corpus = tmp_path / "tools/fuzz/corpus/url"
    corpus.mkdir(parents=True)
    (corpus / "url.txt").write_text("https://seed.example/", encoding="utf-8")
    mocker.patch("fuzz.round_trip_oracles._ROOT", tmp_path)
    seeds = ORACLES["normalize-url-fixpoint"].seeds()
    assert (seeds[:2], len(seeds) > 100, "ignored" in seeds) == (
        ["HTTP://Example.COM:80/", "https://seed.example/"],
        True,
        False,
    )


def test_url_cli_emits_successful_cleaning_rejection(mocker: MockerFixture, tmp_path: Path) -> None:
    source = "HTTP://Example.COM:80/?utm_source=x"
    oracle = replace(
        ORACLES["clean-url-fixpoint"],
        check=partial(clean_url_check, clean=_drop_cleaned_url),
        seeds=lambda: [source],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"clean-url-fixpoint": oracle}, clear=True)
    status = main(["--minutes", "0", "--crash-dir", str(tmp_path)])
    findings = list(tmp_path.glob("*.json"))
    sidecar = json.loads(findings[0].read_text(encoding="utf-8"))
    minimized = findings[0].with_suffix("").read_text(encoding="utf-8")
    assert (
        status,
        len(findings),
        sidecar,
        findings[0].stem,
        clean_url_check(minimized, _drop_cleaned_url),
    ) == (
        1,
        1,
        {"oracle": "clean-url-fixpoint", "detail": "rejects its own output", "hits": 1, "rng_seed": 0},
        f"crash-{hashlib.sha256(minimized.encode()).hexdigest()}",
        "rejects its own output",
    )


def _drop_cleaned_url(text: str) -> str | None:
    return None if text == "http://example.com/" else clean_url(text)
