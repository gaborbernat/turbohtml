from __future__ import annotations

import io
import sys
from typing import TYPE_CHECKING

import pytest
from fuzz.atheris_header import Header
from fuzz.atheris_registry import Target, validate_owners

from turbohtml.__main__ import main

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_atheris_registry_executes_qualified_owner(mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
    def minify(data: bytes) -> None:
        mocker.patch.object(sys, "stdin", io.StringIO(data.decode()))
        assert main(["minify-css"]) == 0

    target = Target("cli-css", minify, ("turbohtml.__main__.main",))
    owners = validate_owners([target], ["turbohtml.__main__"])
    owners["turbohtml.__main__.main"].callback(b"a { color: red }")
    assert capsys.readouterr().out == "a{color:red}"


@pytest.mark.parametrize(
    ("exports", "expected"),
    [
        pytest.param((), "missing=['turbohtml.__main__.main'], unknown=[]", id="missing"),
        pytest.param(
            ("turbohtml.__main__.extra",),
            "missing=['turbohtml.__main__.main'], unknown=['turbohtml.__main__.extra']",
            id="unknown",
        ),
    ],
)
def test_atheris_registry_rejects_ownership_gap(exports: tuple[str, ...], expected: str) -> None:
    target = Target("unassigned", print, exports)
    with pytest.raises(ValueError, match="Export ownership mismatch") as raised:
        validate_owners([target], ["turbohtml.__main__"])
    assert str(raised.value) == f"Export ownership mismatch: {expected}"


def test_atheris_registry_rejects_duplicate_qualified_owner() -> None:
    target = Target("duplicate", print, ("turbohtml.__main__.main",))
    with pytest.raises(ValueError, match=r"Duplicate export owners: turbohtml\.__main__\.main"):
        validate_owners([target, target], ["turbohtml.__main__"])


def test_atheris_registry_rejects_duplicate_target_name() -> None:
    targets = [Target("same", print, ("first.export",)), Target("same", print, ("second.export",))]
    with pytest.raises(ValueError, match="Duplicate target names"):
        validate_owners(targets, [])


def test_atheris_registry_runs_whole_payload_without_chunked_consumer() -> None:
    seen: list[bytes] = []
    Target("whole", seen.append, ()).run(b"payload", Header(1, 2, 3))
    assert seen == [b"payload"]


def test_atheris_registry_runs_chunked_consumer_with_header() -> None:
    seen: list[tuple[bytes, Header]] = []
    Target("chunked", print, (), (), lambda payload, header: seen.append((payload, header))).run(
        b"payload", Header(1, 2, 3)
    )
    assert seen == [(b"payload", Header(1, 2, 3))]
