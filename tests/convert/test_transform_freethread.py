"""Concurrent calls through one compiled stylesheet must not share execution state."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import turbohtml
from turbohtml.transform import Transform

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_transform_compiled_state_is_thread_safe() -> None:
    sheet = turbohtml.parse_xml(
        '<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
        '<xsl:output method="text"/><xsl:param name="suffix"/>'
        '<xsl:template match="/"><xsl:value-of select="concat(r/v, $suffix)"/></xsl:template></xsl:stylesheet>'
    )
    convert = Transform(sheet)
    barrier = threading.Barrier(4)
    results = [""] * 4

    def worker(index: int) -> None:
        barrier.wait()
        results[index] = convert(turbohtml.parse_xml(f"<r><v>{index}</v></r>"), suffix=f"'-{index}'")

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == ["0-0", "1-1", "2-2", "3-3"]


def test_transform_constructor_snapshots_stylesheet_before_import_io(tmp_path: Path, mocker: MockerFixture) -> None:
    (tmp_path / "imported.xsl").write_text(
        '<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"/>', encoding="utf-8"
    )
    sheet = turbohtml.parse_xml(
        '<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
        '<xsl:import href="imported.xsl"/><xsl:output method="text"/>'
        '<xsl:template match="/"><xsl:value-of select="\'before\'"/></xsl:template></xsl:stylesheet>'
    )
    read_started = threading.Event()
    continue_read = threading.Event()
    read_text = Path.read_text

    def blocking_read_text(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
        read_started.set()
        continue_read.wait(timeout=5)
        return read_text(path, encoding, errors)

    mocker.patch.object(Path, "read_text", autospec=True, side_effect=blocking_read_text)
    with ThreadPoolExecutor(max_workers=1) as executor:
        compiled = executor.submit(Transform, sheet, base_url=str(tmp_path / "main.xsl"), import_root=tmp_path)
        try:
            assert read_started.wait(timeout=5)
            value_of = sheet.find("xsl:value-of")
            assert value_of is not None
            value_of.attrs["select"] = "'after'"
        finally:
            continue_read.set()
        convert = compiled.result(timeout=5)

    assert convert(turbohtml.parse_xml("<r/>")) == "before"
