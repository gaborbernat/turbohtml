"""Verify the tree builder against the html5lib tree-construction suite.

The ``.dat`` files under ``tests/html5lib-tests/tree-construction`` give, for
each input, the document tree a conformant parser must build, serialized in the
``| ``-indented "#document" format. This harness parses each ``#data`` block and
compares ``turbohtml``'s serialization against the ``#document`` expectation.
Every case must pass; scripting-enabled cases are excluded because they need a
script-executing host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from turbohtml import _html

_TREE_DIR = Path(__file__).parent / "html5lib-tests" / "tree-construction"


def _parse_dat(path: Path) -> list[tuple[str, str, bool, str | None]]:
    """Return (input, expected-document, script-on, fragment-context) per block."""
    cases: list[tuple[str, str, bool, str | None]] = []
    with path.open(encoding="utf-8", newline="") as handle:  # a literal \r in a case is data
        raw_text = handle.read()
    for raw in raw_text.split("\n#data\n"):
        block = raw.removeprefix("#data\n")
        data, _, rest = block.partition("\n#errors")
        document_marker = "\n#document\n"
        if document_marker not in rest:
            continue
        before, _, document = rest.partition(document_marker)
        script_on = "#script-on" in before
        context: str | None = None
        if "#document-fragment\n" in before:
            context = before.partition("#document-fragment\n")[2].splitlines()[0].strip()
        cases.append((data, document.rstrip("\n"), script_on, context))
    return cases


def _iter_cases() -> list[tuple[str, str, str, str | None]]:
    cases: list[tuple[str, str, str, str | None]] = []
    for path in sorted(_TREE_DIR.glob("*.dat")):
        for data, document, script_on, context in _parse_dat(path):
            if script_on:  # scripting-enabled cases need a script-executing host
                continue
            cases.append((path.name, data, document, context))
    return cases


_CASES = _iter_cases()


def _build(data: str, context: str | None) -> str:
    if context is not None:
        return _html._parse_fragment(data, context).rstrip("\n")
    return _html._parse_tree(data).rstrip("\n")


@pytest.mark.parametrize("filename", sorted({name for name, _, _, _ in _CASES}))
def test_tree_construction(filename: str) -> None:
    cases = [(d, doc, ctx) for name, d, doc, ctx in _CASES if name == filename]
    assert cases, f"no cases parsed from {filename}"
    failures = [
        f"#data {data!r} (context={context!r})\nexpected:\n{document}\ngot:\n{_build(data, context)}"
        for data, document, context in cases
        if _build(data, context) != document
    ]
    assert not failures, f"{filename}: {len(failures)}/{len(cases)} failing\n\n" + "\n\n".join(failures[:5])
