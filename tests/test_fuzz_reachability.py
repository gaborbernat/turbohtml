from __future__ import annotations

import inspect
import json
from typing import TYPE_CHECKING, Final

import pytest
from coverage import CoverageData
from fuzz.atheris_targets import public_targets
from fuzz.oss_fuzz import atheris_target_names, fuzzer_name
from fuzz.reachability import main, target_functions, unreached

if TYPE_CHECKING:
    from pathlib import Path

    from fuzz.atheris_registry import Target

_TARGETS: Final = {target.name: target for target in public_targets()}


@pytest.mark.parametrize(
    ("target", "names"),
    [
        pytest.param("xml-transform", ["_transform", "Transform", "strparam", "transform"], id="functions-and-class"),
        pytest.param("dom-construction", ["_check", "ElementMaker", "document"], id="partial-and-alias"),
        pytest.param("dom-rewrite", ["_check", "rewrite"], id="protocol-stubs"),
        pytest.param("dom-range", ["_check"], id="c-types"),
    ],
)
def test_reachability_target_functions_follow_registry(target: str, names: list[str]) -> None:
    assert [function.name for function in target_functions(_TARGETS[target])] == names


def test_reachability_skips_def_line() -> None:
    callback: Final = target_functions(_TARGETS["html-document"])[0]
    assert inspect.getsourcelines(_TARGETS["html-document"].callback)[1] not in callback.lines


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        pytest.param(set(), [], id="all-reached"),
        pytest.param({"_transform"}, ["_transform"], id="callback-unreached"),
        pytest.param({"Transform", "strparam"}, ["Transform", "strparam"], id="exports-unreached"),
    ],
)
def test_reachability_unreached_names_zero_coverage(tmp_path: Path, missing: set[str], expected: list[str]) -> None:
    target: Final = _TARGETS["xml-transform"]
    _record(tmp_path, target, missing)
    assert unreached(target, tmp_path) == expected


def test_reachability_matches_path_suffix_only(tmp_path: Path) -> None:
    target: Final = _TARGETS["xml-transform"]
    data: Final = CoverageData(basename=str(tmp_path / f"coverage_d_{fuzzer_name(target.name)}"))
    data.add_lines({f"/medio/other_{function.path}": sorted(function.lines) for function in target_functions(target)})
    data.write()
    assert unreached(target, tmp_path) == ["_transform", "Transform", "strparam", "transform"]


def test_reachability_missing_data_file(tmp_path: Path) -> None:
    assert unreached(_TARGETS["xml-transform"], tmp_path) == ["no coverage data at coverage_d_fuzz_xml_transform"]


@pytest.mark.parametrize(
    ("unrecorded", "status"),
    [
        pytest.param(None, 0, id="every-floor-met"),
        pytest.param("html-document", 1, id="one-target-without-data"),
    ],
)
def test_reachability_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], unrecorded: str | None, status: int
) -> None:
    for name in atheris_target_names():
        if name != unrecorded:
            _record(tmp_path, _TARGETS[name], set())
    assert (main(["--coverage-dir", str(tmp_path)]), json.loads(capsys.readouterr().out)) == (
        status,
        {
            name: [f"no coverage data at coverage_d_{fuzzer_name(name)}"] if name == unrecorded else []
            for name in atheris_target_names()
        },
    )


def _record(directory: Path, target: Target, missing: set[str]) -> None:
    data: Final = CoverageData(basename=str(directory / f"coverage_d_{fuzzer_name(target.name)}"))
    executed: dict[str, set[int]] = {}
    for function in target_functions(target):
        if function.name not in missing:
            executed.setdefault(f"/pythoncovmergedfiles/medio/{function.path}", set()).update(function.lines)
    data.add_lines({path: sorted(lines) for path, lines in executed.items()})
    data.write()
