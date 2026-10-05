from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest
from fuzz.fuzz import main

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(("round-trip", "none", "clean-url-fixpoint", True), id="first-checkout"),
        pytest.param(("round-trip", "sanitizer", "normalize-url-fixpoint", True), id="extend-old-checkout"),
        pytest.param(("round-trip", "both", "clean-url-fixpoint", False), id="reuse-complete-checkout"),
        pytest.param(("release-diff", "none", "html", False), id="release-does-not-fetch"),
        pytest.param(("round-trip", "none", "html-fixpoint", False), id="unrelated-oracle"),
        pytest.param(("round-trip", "none", None, True), id="all-oracles"),
        pytest.param(("round-trip", "none", "--oracle=normalize-url-fixpoint", True), id="equals-selection"),
    ],
)
def test_fuzz_cli_prepares_url_seeds(
    mocker: MockerFixture, tmp_path: Path, scenario: tuple[str, str, str | None, bool]
) -> None:
    mode, prepared, oracle, fetch = scenario
    if prepared != "none":
        (tmp_path / "tools/fuzz-data/wpt/sanitizer-api").mkdir(parents=True)
    if prepared == "both":
        urls = tmp_path / "tools/fuzz-data/wpt/url/resources/urltestdata.json"
        urls.parent.mkdir(parents=True)
        urls.write_text("[]", encoding="utf-8")
    selection = [] if oracle is None else [oracle] if oracle.startswith("--oracle=") else ["--oracle", oracle]
    mocker.patch("fuzz.fuzz._ROOT", tmp_path)
    mocker.patch.object(
        sys,
        "argv",
        [
            "fuzz.py",
            "--mode",
            mode,
            "--minutes",
            "0",
            "--crash-dir",
            str(tmp_path / "crashes"),
            *selection,
        ],
    )
    run = mocker.patch(
        "fuzz.fuzz.subprocess.run",
        autospec=True,
        return_value=mocker.MagicMock(returncode=2, stdout=str(tmp_path / "runtime")),
    )
    status = main()
    commands = [call.args[0] for call in run.call_args_list]
    sparse = [command for command in commands if "sparse-checkout" in command]
    child = commands[-1]
    assert (status, sparse, child[1:3], child[7:]) == (
        2,
        [
            [
                "git",
                "-C",
                "tools/fuzz-data/wpt",
                "sparse-checkout",
                "set",
                "--no-cone",
                "/sanitizer-api/",
                "/url/resources/urltestdata.json",
                "/LICENSE.md",
            ]
        ]
        if fetch
        else [],
        ["-m", "fuzz.round_trip_oracles" if mode == "round-trip" else "fuzz.release_diff"],
        selection,
    )
