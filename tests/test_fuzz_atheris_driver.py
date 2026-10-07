from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import pytest
from fuzz.atheris_driver import fuzz
from fuzz.atheris_registry import Target

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture


def test_atheris_driver_connects_exception_boundary(mocker: MockerFixture) -> None:
    accepted: list[bytes] = []
    rejected: list[int] = []

    def consume(data: bytes) -> None:
        if data == b"invalid":
            message = "documented error"
            raise UnicodeError(message)
        accepted.append(data)

    target = Target("cli", consume, ("turbohtml.__main__.main",), (UnicodeError,))
    runtime = mocker.MagicMock(spec=["Setup", "Fuzz", "instrument_func", "instrument_all"])
    runtime.instrument_func.side_effect = lambda callback: callback
    mocker.patch("fuzz.atheris_driver.import_module", autospec=True, return_value=runtime)
    mocker.patch("fuzz.atheris_driver.rejection_hook", autospec=True, return_value=partial(rejected.append, 1))

    def native_loop() -> None:
        callback: Callable[[bytes], None] = runtime.Setup.call_args.args[1]
        callback(b"invalid")
        callback(b"valid")

    runtime.Fuzz.side_effect = native_loop
    fuzz([target], ["turbohtml.__main__"], "cli", ["driver", "-runs=2"])
    runtime.instrument_all.assert_called_once_with()
    assert (accepted, rejected, runtime.Setup.call_args.args[0], runtime.Setup.call_args.kwargs) == (
        [b"valid"],
        [1],
        ["driver", "-runs=2"],
        {"custom_mutator": None},
    )


def test_atheris_driver_rejects_gap_before_runtime(mocker: MockerFixture) -> None:
    load = mocker.patch("fuzz.atheris_driver.import_module", autospec=True)
    with pytest.raises(ValueError, match="Export ownership mismatch"):
        fuzz([], ["turbohtml.__main__"], "cli", ["driver"])
    assert load.call_count == 0
