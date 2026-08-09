"""The native HTML tree builder checked against the pinned living WPT corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, TypedDict, cast

import pytest

from turbohtml import _html


class _Case(TypedDict):
    file: str
    data: str
    document: str
    context: str | None
    scripting: bool | None
    spec_document: str


class _Corpus(TypedDict):
    source: str
    revision: str
    files: list[str]
    fixture_counts: dict[str, int]
    non_script_fixture_counts: dict[str, int]
    cases: list[_Case]


_CORPUS_PATH: Final = Path(__file__).parent / "data" / "wpt_html_tree.json"
if not _CORPUS_PATH.is_file():
    msg = f"{_CORPUS_PATH} is absent; regenerate it with tools/generate_wpt_tree_corpus.py"
    raise RuntimeError(msg)
_CORPUS: Final = cast("_Corpus", json.loads(_CORPUS_PATH.read_text(encoding="utf-8")))
_CASES: Final = tuple(case for case in _CORPUS["cases"] if case["scripting"] is None)


def _build(case: _Case) -> str:
    if (context := case["context"]) is not None:
        result = _html._parse_fragment(
            case["data"],
            context,
            False,  # ruff:ignore[boolean-positional-value-in-call]  # positional-only native hook
        )
    else:
        result = _html._parse_tree(
            case["data"],
            False,  # ruff:ignore[boolean-positional-value-in-call]  # positional-only native hook
        )
    return result.rstrip("\n")


def test_wpt_corpus_source_and_counts_are_pinned() -> None:
    assert _CORPUS["source"] == (
        "https://github.com/web-platform-tests/wpt/tree/4830edb033cb486fd0cd6f85b5e937cfc718704d/"
        "html/syntax/parsing/resources"
    )
    assert _CORPUS["revision"] == "4830edb033cb486fd0cd6f85b5e937cfc718704d"
    assert len(_CORPUS["files"]) == 61
    assert len(_CORPUS["cases"]) == 1920
    assert len(_CASES) == 1880
    assert sum(_CORPUS["fixture_counts"].values()) == 1920
    assert sum(_CORPUS["non_script_fixture_counts"].values()) == 1880
    assert _CORPUS["non_script_fixture_counts"]["processing-instructions.dat"] == 123


def test_raw_wpt_mismatches_are_the_eight_documented_foreign_cases() -> None:
    mismatches = {(case["file"], case["data"], case["context"]) for case in _CASES if _build(case) != case["document"]}
    assert mismatches == {
        ("tests26.dat", "<svg></p><foo>", None),
        ("tests26.dat", "<math></p><foo>", None),
        ("foreign-fragment.dat", "<svg></p><foo>", "div"),
        ("foreign-fragment.dat", "</p><foo>", "svg svg"),
        ("tests26.dat", "<svg></br><foo>", None),
        ("tests26.dat", "<math></br><foo>", None),
        ("foreign-fragment.dat", "<svg></br><foo>", "div"),
        ("foreign-fragment.dat", "</br><foo>", "svg svg"),
    }


@pytest.mark.parametrize("filename", _CORPUS["files"])
def test_spec_adjusted_wpt_tree_construction(filename: str) -> None:
    cases = [case for case in _CASES if case["file"] == filename]
    failures = [
        f"data={case['data']!r}, context={case['context']!r}\nexpected:\n{case['spec_document']}\ngot:\n{result}"
        for case in cases
        if (result := _build(case)) != case["spec_document"]
    ]
    assert not failures, f"{filename}: {len(failures)}/{len(cases)} failed\n\n" + "\n\n".join(failures[:5])
