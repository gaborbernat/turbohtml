from __future__ import annotations

import json
from typing import Final

import pytest
from fuzz import resource_canary


@pytest.mark.parametrize("escape", sorted(resource_canary.ESCAPES))
def test_resource_canary_escape_stays_contained(escape: str) -> None:
    attempt: Final = resource_canary.Attempt(0, escape, "canary0123456789abcdef")
    assert [(row.engine, row.leaked) for row in resource_canary.compare(attempt)] == [
        ("xslt", False),
        ("relaxng", False),
    ]


@pytest.mark.parametrize("escape", ["parent", "symlink"])
def test_resource_canary_inside_root_is_observed(escape: str) -> None:
    attempt: Final = resource_canary.Attempt(0, escape, "canary0123456789abcdef")
    assert [(row.engine, row.leaked) for row in resource_canary.compare(attempt, negative_control=True)] == [
        ("xslt", True),
        ("relaxng", True),
    ]


def test_resource_canary_generate_is_seeded() -> None:
    assert [resource_canary.generate(seed) == resource_canary.generate(5) for seed in (5, 6)] == [True, False]


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        pytest.param(["--cases", "3"], (0, {"cases": 3, "findings": 0}), id="contained"),
        pytest.param(["--cases", "1", "--negative-control"], (1, {"cases": 1, "findings": 2}), id="negative-control"),
    ],
)
def test_resource_canary_cli(
    capsys: pytest.CaptureFixture[str], arguments: list[str], expected: tuple[int, dict[str, int]]
) -> None:
    status: Final = resource_canary.main(arguments)
    assert (status, json.loads(capsys.readouterr().out.splitlines()[-1])["summary"]) == expected


def test_resource_canary_cli_rejects_case_count(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        resource_canary.main(["--cases", "0"])
    assert "--cases must be between 1 and 256" in capsys.readouterr().err
