"""
Extract and check the living WPT HTML tree-construction corpus.

The browser suite is too large to vendor. This script copies its compact ``.dat`` parser oracles into a committed JSON
file, records the source revision, and runs turbohtml's native tree builder against every case. Eight historical
foreign-content expectations conflict with the living tree-construction algorithm; the corpus records both the raw WPT
tree and the normatively adjusted tree for those cases.

Usage: python tools/generate_wpt_tree_corpus.py WPT_CHECKOUT tests/conformance/data/wpt_html_tree.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Final, TypedDict

from turbohtml import _html  # ruff:ignore[import-private-name]  # the report exercises the native conformance dumper


class _Case(TypedDict):
    file: str
    data: str
    document: str
    context: str | None
    scripting: bool | None
    spec_document: str


# WHATWG's foreign-content "any other end tag" rule leaves the foreign root current before reprocessing. The eight WPT
# fixtures below expect an older pop. Keep both trees visible until https://github.com/tox-dev/turbohtml/issues/32 and
# https://github.com/tox-dev/turbohtml/issues/63 are resolved against
# https://html.spec.whatwg.org/multipage/parsing.html#parsing-main-inforeign.
_FOREIGN_CONTENT_OVERRIDES: Final = {
    ("tests26.dat", "<svg></p><foo>", None): (
        "| <html>\n|   <head>\n|   <body>\n|     <svg svg>\n|       <p>\n|       <svg foo>"
    ),
    ("tests26.dat", "<math></p><foo>", None): (
        "| <html>\n|   <head>\n|   <body>\n|     <math math>\n|       <p>\n|       <math foo>"
    ),
    ("foreign-fragment.dat", "<svg></p><foo>", "div"): "| <svg svg>\n|   <p>\n|   <svg foo>",
    ("foreign-fragment.dat", "</p><foo>", "svg svg"): "| <svg foo>",
    ("tests26.dat", "<svg></br><foo>", None): (
        "| <html>\n|   <head>\n|   <body>\n|     <svg svg>\n|       <br>\n|       <svg foo>"
    ),
    ("tests26.dat", "<math></br><foo>", None): (
        "| <html>\n|   <head>\n|   <body>\n|     <math math>\n|       <br>\n|       <math foo>"
    ),
    ("foreign-fragment.dat", "<svg></br><foo>", "div"): "| <svg svg>\n|   <br>\n|   <svg foo>",
    ("foreign-fragment.dat", "</br><foo>", "svg svg"): "| <svg foo>",
}


def _revision(checkout: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _parse_file(path: Path) -> list[_Case]:
    with path.open(encoding="utf-8", newline="") as handle:
        source = handle.read()
    cases: list[_Case] = []
    for block in source.split("#data\n")[1:]:
        before_document, marker, document = block.partition("\n#document\n")
        if not marker:
            msg = f"{path}: #data block has no #document section"
            raise ValueError(msg)
        sections: dict[str, int] = {}
        for name in ("errors", "new-errors", "document-fragment", "script-on", "script-off"):
            heading = f"#{name}"
            if before_document.startswith(heading):
                sections[name] = 0
            elif (position := before_document.find(f"\n{heading}")) >= 0:
                sections[name] = position + 1
        data_end = (
            min(position if position == 0 else position - 1 for position in sections.values()) if sections else None
        )
        data = before_document[:data_end]
        context = None
        if (fragment_start := sections.get("document-fragment")) is not None:
            context = before_document[fragment_start + len("#document-fragment\n") :].splitlines()[0].strip()
        key = (path.name, data, context)
        scripting = True if "script-on" in sections else False if "script-off" in sections else None
        cases.append({
            "file": path.name,
            "data": data,
            "document": document.rstrip("\n"),
            "context": context,
            "scripting": scripting,
            "spec_document": _FOREIGN_CONTENT_OVERRIDES.get(key, document.rstrip("\n")),
        })
    return cases


def _build(case: _Case) -> str:
    if (context := case["context"]) is not None:
        # The private dumper is the native html5lib/WPT oracle surface and avoids public-serializer adapter artifacts.
        result = _html._parse_fragment(  # ruff:ignore[private-member-access]
            case["data"], context, bool(case["scripting"])
        )
    else:
        result = _html._parse_tree(  # ruff:ignore[private-member-access]
            case["data"], bool(case["scripting"])
        )
    return result.rstrip("\n")


def _report(cases: list[_Case]) -> None:
    cases = [case for case in cases if case["scripting"] is None]
    raw_failures: list[tuple[_Case, str]] = []
    adjusted_failures: list[tuple[_Case, str]] = []
    for case in cases:
        result = _build(case)
        if result != case["document"]:
            raw_failures.append((case, result))
        if result != case["spec_document"]:
            adjusted_failures.append((case, result))
    for filename in sorted({case["file"] for case in cases}):
        fixture = [case for case in cases if case["file"] == filename]
        raw = len(fixture) - sum(case["file"] == filename for case, _ in raw_failures)
        adjusted = len(fixture) - sum(case["file"] == filename for case, _ in adjusted_failures)
        print(f"{filename}: raw {raw}/{len(fixture)}, spec-adjusted {adjusted}/{len(fixture)}")
    count = len(cases)
    print(f"raw: {count - len(raw_failures)}/{count} ({(count - len(raw_failures)) / count:.2%})")
    print(f"spec-adjusted: {count - len(adjusted_failures)}/{count} ({(count - len(adjusted_failures)) / count:.2%})")
    print(f"normative exclusions: {sum(case['document'] != case['spec_document'] for case in cases)}")
    if adjusted_failures:
        for case, result in adjusted_failures:
            print(
                f"{case['file']}: data={case['data']!r}, context={case['context']!r}, scripting={case['scripting']}\n"
                f"expected:\n{case['spec_document']}\ngot:\n{result}"
            )
        msg = f"{len(adjusted_failures)} spec-adjusted WPT cases failed"
        raise SystemExit(msg)


def generate(checkout: Path, out_path: Path) -> None:
    """Write the pinned corpus and fail if its non-script adjusted cases diverge."""
    resources = checkout / "html" / "syntax" / "parsing" / "resources"
    files = sorted(resources.glob("*.dat"))
    if not files:
        msg = f"no HTML tree-construction .dat files found under {resources}"
        raise SystemExit(msg)
    cases = [case for path in files for case in _parse_file(path)]
    revision = _revision(checkout)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "source": "https://github.com/web-platform-tests/wpt/tree/master/html/syntax/parsing/resources",
                "revision": revision,
                "files": [path.name for path in files],
                "fixture_counts": {path.name: sum(case["file"] == path.name for case in cases) for path in files},
                "non_script_fixture_counts": {
                    path.name: sum(case["file"] == path.name and case["scripting"] is None for case in cases)
                    for path in files
                },
                "cases": cases,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_path}: {len(cases)} cases from {len(files)} files at {revision[:12]}")
    _report(cases)


__all__ = ["generate"]


if __name__ == "__main__":
    if len(sys.argv) != 3:
        msg = "usage: generate_wpt_tree_corpus.py WPT_CHECKOUT OUTPUT_JSON"
        raise SystemExit(msg)
    generate(Path(sys.argv[1]), Path(sys.argv[2]))
