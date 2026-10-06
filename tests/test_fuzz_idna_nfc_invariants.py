from __future__ import annotations

import random
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.idna_nfc_oracles import (
    UnsupportedIdnaNfcCaseError,
    idna_nfc_check,
    idna_nfc_controls,
    idna_nfc_generate,
    idna_nfc_seeds,
)
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main

from turbohtml.extract import normalize_url

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("case", "source", "expected"),
    [
        pytest.param("reorder:", "q\u0301\u0323", "xn--q-xbb5h", id="reorder"),
        pytest.param("blocked:", "a\u0305\u0301", "xn--a-xbbl", id="blocked"),
        pytest.param("successive-compose:", "a\u030a\u0301", "xn--3ka", id="successive-compose"),
        pytest.param("noncomposing-tail:", "s\u0323\u0301", "xn--lsa331l", id="noncomposing-tail"),
        pytest.param("lower-class-intervening:", "a\u0316\u0301", "xn--1ca44i", id="lower-class-intervening"),
        pytest.param("hangul-lv:", "\u1100\u1161", "xn--o39a", id="hangul-lv"),
        pytest.param("hangul-lvt:", "\u1100\u1161\u11a8", "xn--p39a", id="hangul-lvt"),
        pytest.param("hangul-lv-plus-t:", "\uac00\u11a8", "xn--p39a", id="hangul-lv-plus-t"),
    ],
)
def test_idna_nfc_pins_public_target(case: str, source: str, expected: str) -> None:
    assert (normalize_url(f"https://{source}.example/"), idna_nfc_check(case)) == (
        f"https://{expected}.example/",
        None,
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("", id="empty"),
        pytest.param("reorder", id="missing-separator"),
        pytest.param("unknown:", id="unknown-family"),
        pytest.param("reorder:A", id="uppercase"),
        pytest.param("reorder:abcdefghi", id="overlong"),
        pytest.param("reorder:a:b", id="extra-separator"),
    ],
)
def test_idna_nfc_rejects_unsupported_grammar(case: str) -> None:
    with pytest.raises(UnsupportedIdnaNfcCaseError):
        idna_nfc_check(case)


@pytest.mark.parametrize(
    ("normalize", "expected"),
    [
        pytest.param(lambda text: text, "canonical host differs from independent target", id="unchanged"),
        pytest.param(
            lambda _text: "https://wrong.example/",
            "canonical host differs from independent target",
            id="stable-wrong-target",
        ),
        pytest.param(lambda _text: _reject(), "rejects known-valid canonical host", id="input-rejection"),
        pytest.param(
            lambda text: _reject() if text.isascii() else normalize_url(text),
            "rejects canonical host output",
            id="output-rejection",
        ),
        pytest.param(
            lambda text: text + "x" if text.isascii() else normalize_url(text),
            "canonical host changes on repeat",
            id="changed-repeat",
        ),
    ],
)
def test_idna_nfc_discriminates_failures(normalize: Callable[[str], str], expected: str) -> None:
    assert idna_nfc_check("reorder:", normalize) == expected


def _reject() -> str:
    msg = "rejected"
    raise ValueError(msg)


def test_idna_nfc_registry_controls_and_seed_floor() -> None:
    seeds: Final = idna_nfc_seeds()
    assert (
        all(idna_nfc_controls().values()),
        len(seeds),
        all(ORACLES["idna-nfc"].check(case) is None for case in seeds),
        ORACLES["idna-nfc"].floor,
    ) == (True, 160, True, Floor(100, 1))


def test_idna_nfc_generated_cases_compare() -> None:
    rng: Final = random.Random(1010)  # ruff: ignore[suspicious-non-cryptographic-random-usage]  # reproduce oracle cases
    assert [idna_nfc_check(idna_nfc_generate(rng)) for _ in range(100)] == [None] * 100


def test_idna_nfc_registry_counts_unsupported_case() -> None:
    with pytest.raises(OutOfScopeError):
        ORACLES["idna-nfc"].check("unknown:")


def test_idna_nfc_cli_detects_stable_wrong_mapping(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["idna-nfc"],
        check=partial(idna_nfc_check, normalize=lambda _text: "https://wrong.example/"),
        seeds=lambda: ["reorder:"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"idna-nfc": oracle}, clear=True)
    assert (
        main(["--minutes", "0", "--crash-dir", str(tmp_path)]),
        len(list(tmp_path.glob("*.json"))),
    ) == (1, 1)
