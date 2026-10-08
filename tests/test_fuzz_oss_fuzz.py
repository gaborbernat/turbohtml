from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from fuzz.atheris_targets import public_targets
from fuzz.oss_fuzz import atheris_target_names, fuzzer_name, main, write_harnesses

if TYPE_CHECKING:
    from pathlib import Path


def test_oss_fuzz_targets_skip_only_node_oracle() -> None:
    assert set(atheris_target_names()) == {target.name for target in public_targets()} - {"javascript"}


@pytest.mark.parametrize(
    ("target", "fuzzer"),
    [
        pytest.param("html-document", "fuzz_html_document", id="dashed"),
        pytest.param("javascript", "fuzz_javascript", id="plain"),
    ],
)
def test_oss_fuzz_fuzzer_name(target: str, fuzzer: str) -> None:
    assert fuzzer_name(target) == fuzzer


def test_oss_fuzz_harness_runs_its_target(tmp_path: Path) -> None:
    script: Final = next(path for path in write_harnesses(tmp_path) if path.name == "fuzz_xml_transform.py")
    assert script.read_text(encoding="utf-8") == (
        "import sys\n\nfrom fuzz.atheris_driver import fuzz\n"
        "from fuzz.atheris_targets import MODULES, public_targets\n\n"
        "fuzz(public_targets(), MODULES, 'xml-transform', sys.argv)\n"
    )


def test_oss_fuzz_cli_prints_one_script_per_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["harnesses", "--output", str(tmp_path)]) == 0
    assert capsys.readouterr().out.split() == [
        str(tmp_path / f"{fuzzer_name(name)}.py") for name in atheris_target_names()
    ]
