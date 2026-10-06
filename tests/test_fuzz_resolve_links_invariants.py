from __future__ import annotations

import json
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.round_trip_oracles import ORACLES, Floor, OutOfScopeError, main, resolve_links_check

from turbohtml import Node, parse_fragment

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture


_BASE: Final = "http://example.test/b/c/d;p?q"


@pytest.mark.parametrize(
    ("case", "reference", "expected"),
    [
        pytest.param("child", "g", "http://example.test/b/c/g", id="child"),
        pytest.param("current", "./g", "http://example.test/b/c/g", id="current"),
        pytest.param("parent", "../g", "http://example.test/b/g", id="parent"),
        pytest.param("grandparent", "../../g", "http://example.test/g", id="grandparent"),
        pytest.param("root", "/g", "http://example.test/g", id="root"),
        pytest.param("query", "?g", "http://example.test/b/c/d;p?g", id="query"),
        pytest.param("fragment", "#g", "http://example.test/b/c/d;p?q#g", id="fragment"),
        pytest.param("directory", "g/", "http://example.test/b/c/g/", id="directory"),
    ],
)
def test_resolve_links_oracle_pins_first_and_repeated_targets(case: str, reference: str, expected: str) -> None:
    document = parse_fragment('<a href="">link</a>')
    document.select("a")[0].attrs["href"] = reference
    document.resolve_links(_BASE)
    first: Final = document.links()[0].url
    document.resolve_links(_BASE)
    assert (first, document.links()[0].url, resolve_links_check(f"{case}:g")) == (expected, expected, None)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("parent", id="missing-separator"),
        pytest.param("unknown:g", id="unknown-case"),
        pytest.param("parent:", id="empty-leaf"),
        pytest.param("parent:g/path", id="path-in-leaf"),
        pytest.param("parent:é", id="unicode-leaf"),
        pytest.param("parent:g" + "1" * 16, id="overlong-leaf"),
    ],
)
def test_resolve_links_oracle_counts_unsupported_grammar(source: str) -> None:
    with pytest.raises(OutOfScopeError):
        resolve_links_check(source)


def _wrong_target(node: Node, _base: str) -> None:
    node.select("a")[0].attrs["href"] = "http://wrong.example/"


def _changed_repeat(node: Node, base: str) -> None:
    if node.links()[0].url.startswith("http:"):
        node.select("a")[0].attrs["href"] = node.links()[0].url + "a"
    else:
        node.resolve_links(base)


@pytest.mark.parametrize(
    ("resolve", "expected"),
    [
        pytest.param(lambda _node, _base: None, "resolution differs from RFC target", id="no-op"),
        pytest.param(_wrong_target, "resolution differs from RFC target", id="stable-wrong-target"),
        pytest.param(_changed_repeat, "resolved link changes on repeat", id="changed-repeat"),
    ],
)
def test_resolve_links_oracle_discriminates_failures(resolve: Callable[[Node, str], None], expected: str) -> None:
    assert resolve_links_check("parent:g", resolve) == expected


def test_resolve_links_registry_checks_seed_batch_and_controls() -> None:
    oracle: Final = ORACLES["resolve-links"]
    seeds: Final = oracle.seeds()
    assert (
        len(seeds),
        len(set(seeds)) >= 100,
        all(oracle.check(seed) is None for seed in seeds),
        oracle.controls(),
    ) == (
        500,
        True,
        True,
        {"unchanged relative link": True, "stable wrong target": True, "changed repeat": True},
    )


def test_resolve_links_cli_compares_seeds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result: Final = main(["--oracle", "resolve-links", "--minutes", "0", "--crash-dir", str(tmp_path)])
    assert (result, list(tmp_path.glob("crash-*")), "resolve-links" in capsys.readouterr().out) == (0, [], True)


def test_resolve_links_cli_writes_wrong_target_finding(mocker: MockerFixture, tmp_path: Path) -> None:
    oracle: Final = replace(
        ORACLES["resolve-links"],
        check=partial(resolve_links_check, resolve=_wrong_target),
        seeds=lambda: ["parent:g"],
        floor=Floor(1, 1),
    )
    mocker.patch.dict(ORACLES, {"resolve-links": oracle}, clear=True)
    result: Final = main(["--oracle", "resolve-links", "--minutes", "0", "--crash-dir", str(tmp_path)])
    findings: Final = list(tmp_path.glob("*.json"))
    payload: Final = json.loads(findings[0].read_text(encoding="utf-8"))
    assert (result, len(findings), payload["oracle"], payload["detail"], payload["hits"]) == (
        1,
        1,
        "resolve-links",
        "resolution differs from RFC target",
        1,
    )


def test_resolve_links_cli_rejects_vacuous_run(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.dict(
        ORACLES,
        {"resolve-links": replace(ORACLES["resolve-links"], seeds=lambda: ["parent"], floor=Floor(1, 1))},
        clear=True,
    )
    assert main(["--oracle", "resolve-links", "--minutes", "0", "--crash-dir", str(tmp_path)]) == 2
