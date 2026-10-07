from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fuzz.fuzz import main as fuzz_main
from fuzz.triage import classify, main

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("report", "kind"),
    [
        pytest.param("ERROR: libFuzzer: timeout after 10 seconds", "timeout", id="timeout"),
        pytest.param("ERROR: libFuzzer: out-of-memory (malloc(64))", "oom", id="oom"),
        pytest.param("AddressSanitizer: rss limit exhausted", "oom", id="rss-limit"),
        pytest.param("MemoryError", "oom", id="python-memory"),
        pytest.param("TimeoutError", "timeout", id="python-timeout"),
        pytest.param("ERROR: AddressSanitizer: heap-buffer-overflow", "crash", id="crash"),
        pytest.param("Killed", "crash", id="unknown-kill"),
    ],
)
def test_triage_classifies_report(report: str, kind: str) -> None:
    assert classify(report).kind == kind


def test_triage_hashes_five_frames_without_addresses_or_build_paths() -> None:
    first = "\n".join(
        f"    #{index} 0x{index + 10:x} in call{index} /first/src/input.c:{index + 1}" for index in range(6)
    )
    second = "\n".join(
        f"    #{index} 0x{index + 100:x} in call{index} /second/src/input.c:{index + 1}" for index in range(5)
    )
    finding = classify(first)
    assert (finding.frames, finding.digest) == (
        tuple(f"call{index} input.c:{index + 1}" for index in range(5)),
        classify(second + "\n    #5 0x567 in changed elsewhere.c:1").digest,
    )


def test_triage_separates_different_top_frames() -> None:
    assert classify("#0 0x12 in original source.c:1").digest != classify("#0 0x23 in changed source.c:1").digest


def test_triage_ignores_allocation_stack() -> None:
    assert classify("#0 0x12 in fault source.c:1\nallocated by thread:\n#0 0x34 in allocator malloc.c:9").frames == (
        "fault source.c:1",
    )


def test_triage_python_innermost_frames_first() -> None:
    report = "Traceback (most recent call last):\n" + "\n".join(
        f'  File "/checkout/case.py", line {index + 1}, in call{index}' for index in range(7)
    )
    assert classify(report).frames == tuple(f"call{index} case.py:{index + 1}" for index in range(6, 1, -1))


def test_triage_resource_classes_keep_separate_hashes() -> None:
    frames = "\n#0 0x12 in same source.c:1"
    assert len({classify(kind + frames).digest for kind in ("TimeoutError", "MemoryError", "crash")}) == 3


def test_triage_frameless_reports_keep_distinct_messages() -> None:
    assert classify("unexpected result A").digest != classify("unexpected result B").digest


def test_triage_unsymbolized_module_offsets() -> None:
    assert classify("#0 0x12 (/tmp/subject+0x1234)").frames == ("(subject+0x1234)",)


def test_triage_cli_groups_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = [tmp_path / name for name in ("first.log", "second.log", "timeout.log")]
    paths[0].write_text("#0 0x12 in fault /first/input.c:3", encoding="utf-8")
    paths[1].write_text("#0 0x34 in fault /second/input.c:3", encoding="utf-8")
    paths[2].write_text("TimeoutError", encoding="utf-8")
    output = tmp_path / "triage.json"
    assert main([*map(str, paths), "--output", str(output)]) == 0
    assert json.loads(output.read_text()) == {
        classify(paths[0].read_text()).digest: {
            "kind": "crash",
            "frames": ["fault input.c:3"],
            "reports": list(map(str, paths[:2])),
        },
        classify("TimeoutError").digest: {"kind": "timeout", "frames": [], "reports": [str(paths[2])]},
    }
    assert capsys.readouterr().out == "triage: 3 reports, 2 groups\n"


@pytest.mark.parametrize(
    "missing", [pytest.param("input", id="missing-input"), pytest.param("output", id="output-parent")]
)
def test_triage_cli_reports_file_errors(tmp_path: Path, missing: str, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source.log"
    if missing == "output":
        source.write_text("error", encoding="utf-8")
    output = tmp_path / "absent" / "triage.json"
    with pytest.raises(SystemExit, match="2"):
        main([str(source), "--output", str(output)])
    assert capsys.readouterr().err.startswith("triage: ")


def test_triage_runner_does_not_build_or_replay(tmp_path: Path) -> None:
    source = tmp_path / "report.log"
    source.write_text("MemoryError", encoding="utf-8")
    output = tmp_path / "groups.json"
    assert fuzz_main(["--mode", "triage", "--build", str(source), "--output", str(output)]) == 0
    assert json.loads(output.read_text()) == {
        classify("MemoryError").digest: {"kind": "oom", "frames": [], "reports": [str(source)]}
    }


def test_triage_runner_rejects_unknown_smoke_arguments() -> None:
    with pytest.raises(SystemExit, match="2"):
        fuzz_main(["--mode", "smoke", "--unknown"])


def test_triage_runner_keeps_release_dispatch(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch("subprocess.run", autospec=True, return_value=mocker.MagicMock(returncode=0))
    assert fuzz_main(["--mode", "release-diff", "--minutes", "0", "--crash-dir", str(tmp_path)]) == 0
