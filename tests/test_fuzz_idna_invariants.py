from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, idna_host_check, main

from turbohtml.extract import normalize_url

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("case", "source", "expected"),
    [
        pytest.param("umlaut\n", "münchen.example", "xn--mnchen-3ya.example", id="umlaut"),
        pytest.param("sharp-s\n", "faß.example", "xn--fa-hia.example", id="nontransitional"),
        pytest.param("acute-decomposed\n", "a\u0301.example", "xn--1ca.example", id="acute-decomposed"),
        pytest.param("acute-precomposed\n", "á.example", "xn--1ca.example", id="acute-precomposed"),
        pytest.param("umlaut-decomposed\n", "u\u0308.example", "xn--tda.example", id="umlaut-decomposed"),
        pytest.param("japanese\n", "日本語.example", "xn--wgv71a119e.example", id="japanese"),
        pytest.param("greek\n", "δοκιμή.example", "xn--jxalpdlp.example", id="greek"),
        pytest.param("ignored\n", "ex\u00adample.example", "example.example", id="ignored-character"),
        pytest.param("fullwidth\n", "\uff26\uff2f\uff2f.example", "foo.example", id="fullwidth"),
        pytest.param("mapped-dot\n", "日本語。\uff2a\uff30.example", "xn--wgv71a119e.jp.example", id="mapped-dot"),
        pytest.param("umlaut\na", "amünchen.example", "xn--amnchen-o2a.example", id="affix"),
    ],
)
def test_idna_invariant_pins_public_output(case: str, source: str, expected: str) -> None:
    url: Final = f"https://{expected}/"
    assert (normalize_url(f"https://{source}/"), normalize_url(url), idna_host_check(case)) == (url, url, None)


@pytest.mark.parametrize("case", ["", "umlaut", "unknown\n", "umlaut\nA", "umlaut\nabcdefghi", "umlaut\na\nb"])
def test_idna_invariant_counts_unsupported_cases(case: str) -> None:
    with pytest.raises(OutOfScopeError):
        idna_host_check(case)


@pytest.mark.parametrize(
    ("normalize", "expected"),
    [
        pytest.param(lambda text: text, "IDNA output is not ASCII", id="unchanged-input"),
        pytest.param(
            lambda _text: "https://wrong.example/", "IDNA host differs from expected mapping", id="wrong-mapping"
        ),
        pytest.param(
            lambda _text: "https://xn--0.example/", "IDNA output has undecodable Punycode", id="invalid-punycode"
        ),
        pytest.param(lambda _text: "https://xn--u-ccb.example/", "IDNA decoded label is not NFC", id="non-nfc"),
        pytest.param(
            lambda _text: "https://xn--mnchen-3yA.example/", "IDNA Punycode is not canonical", id="noncanonical"
        ),
        pytest.param(lambda _text: _reject(), "rejects known-valid Unicode host", id="input-rejection"),
        pytest.param(
            lambda text: _reject() if text.isascii() else normalize_url(text),
            "rejects canonical IDNA output",
            id="output-rejection",
        ),
        pytest.param(
            lambda text: text + "a" if text.isascii() else normalize_url(text),
            "IDNA output is not a fixpoint",
            id="unstable-output",
        ),
    ],
)
def test_idna_invariant_discriminates_failures(normalize: Callable[[str], str], expected: str) -> None:
    assert idna_host_check("umlaut\n", normalize) == expected


def _reject() -> str:
    msg = "rejected"
    raise ValueError(msg)


def test_idna_registry_has_discriminating_controls_and_seed_floor() -> None:
    oracle: Final = ORACLES["idna-host"]
    seeds: Final = oracle.seeds()
    assert (
        all(oracle.controls().values()),
        len(seeds),
        all(oracle.check(case) is None for case in seeds),
        oracle.floor,
    ) == (
        True,
        160,
        True,
        Floor(100, 0.95),
    )


def test_idna_cli_writes_mapping_failure(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["idna-host"],
        check=partial(idna_host_check, normalize=lambda text: text),
        seeds=lambda: ["umlaut\n"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"idna-host": oracle}, clear=True)
    status: Final = main(["--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    assert len(findings) == 1
    minimized: Final = findings[0].with_suffix("").read_text(encoding="utf-8")
    assert (
        status,
        json.loads(findings[0].read_text()),
        findings[0].stem,
        idna_host_check(minimized, lambda text: text),
    ) == (
        1,
        {"oracle": "idna-host", "detail": "IDNA output is not ASCII", "hits": 1, "rng_seed": 0},
        f"crash-{hashlib.sha256(minimized.encode()).hexdigest()}",
        "IDNA output is not ASCII",
    )
