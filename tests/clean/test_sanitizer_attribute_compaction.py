from __future__ import annotations

from dataclasses import replace
from typing import Final, cast

import pytest
from bench.operations import INPUTS

from turbohtml import parse_fragment
from turbohtml.clean import Policy, Removed, Sanitizer


@pytest.fixture
def policy() -> Policy:
    return Policy(
        tags=frozenset({"a"}),
        attributes={"a": frozenset({"href", "title", "id", "style"})},
        attribute_prefixes=frozenset({"data-"}),
        css_properties=frozenset({"color"}),
    )


@pytest.mark.parametrize("count", [0, 31, 32, 1_024])
@pytest.mark.parametrize("prefix", ["bad-", "data-"], ids=["rejected", "allowed"])
def test_attribute_compaction_count(policy: Policy, count: int, prefix: str) -> None:
    attributes: Final = "".join(f' {prefix}{index}="x"' for index in range(count))
    assert Sanitizer(policy).sanitize(f"<a{attributes}>x</a>") == (
        f"<a{attributes}>x</a>" if prefix == "data-" else "<a>x</a>"
    )


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        pytest.param('href="javascript:alert(1)"', "", id="unsafe-url"),
        pytest.param('onclick="alert(1)"', "", id="event-handler"),
        pytest.param('style="color: red; position: fixed"', ' style="color: red"', id="style-safety"),
        pytest.param('href="/safe"', ' href="/safe"', id="safe-url"),
    ],
)
def test_attribute_compaction_safety(policy: Policy, attribute: str, expected: str) -> None:
    rejected: Final = "".join(f' bad-{index}="x"' for index in range(32))
    assert Sanitizer(policy).sanitize(f"<a{rejected} {attribute}>x</a>") == f"<a{expected}>x</a>"


def test_attribute_compaction_retains_order(policy: Policy) -> None:
    attributes: Final = "".join(f' bad-{index}="x" data-{index}="{index}"' for index in range(32))
    expected: Final = "".join(f' data-{index}="{index}"' for index in range(32))
    assert Sanitizer(policy).sanitize(f"<a{attributes}>x</a>") == f"<a{expected}>x</a>"


def test_attribute_compaction_report_order(policy: Policy) -> None:
    rejected: Final = "".join(f' bad-{index}="x"' for index in range(32))
    assert Sanitizer(policy).sanitize_report(f'<a first="x" href="javascript:x" onclick="x"{rejected}>x</a>') == (
        "<a>x</a>",
        [Removed("a", name) for name in ("first", "href", "onclick", *(f"bad-{index}" for index in range(32)))],
    )


def test_attribute_compaction_filter_order(policy: Policy) -> None:
    names: Final[list[str]] = []

    def record(_tag: str, name: str, value: str) -> str:
        names.append(name)
        return value

    attributes: Final = "".join(f' bad-{index}="x" data-{index}="x"' for index in range(32))
    Sanitizer(replace(policy, attribute_filter=record)).sanitize(f"<a{attributes}>x</a>")
    assert names == [f"data-{index}" for index in range(32)]


@pytest.mark.parametrize("prefix", ["bad-", "data-"], ids=["custom-attributes", "custom-element"])
def test_attribute_compaction_custom_checks(policy: Policy, prefix: str) -> None:
    attributes: Final = "".join(f' {prefix}{index}="x"' for index in range(32))
    sanitizer: Final = Sanitizer(
        replace(
            policy,
            custom_element_check=lambda tag: tag == "x-card",
            custom_attribute_check=(lambda _tag, name: name.startswith("bad-")) if prefix == "bad-" else None,
        )
    )
    assert sanitizer.sanitize(f"<x-card{attributes}>x</x-card>") == f"<x-card{attributes}>x</x-card>"


def test_attribute_compaction_late_writes(policy: Policy) -> None:
    rejected: Final = "".join(f' bad-{index}="x"' for index in range(32))
    sanitizer: Final = Sanitizer(
        replace(policy, set_attributes={"a": {"href": "javascript:x", "title": "kept", "onclick": "x"}})
    )
    assert sanitizer.sanitize(f"<a{rejected}>x</a>") == '<a title="kept">x</a>'


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        pytest.param('id="heading"', 'id="user-content-heading"', id="named-property"),
        pytest.param('title="{{value}}"', 'title=" "', id="template-marker"),
    ],
)
def test_attribute_compaction_value_rewrites(policy: Policy, attribute: str, expected: str) -> None:
    rejected: Final = "".join(f' bad-{index}="x"' for index in range(32))
    sanitizer: Final = Sanitizer(replace(policy, isolate_named_props=True, strip_template_markers=True))
    assert sanitizer.sanitize(f"<a{rejected} {attribute}>x</a>") == f"<a {expected}>x</a>"


def test_attribute_compaction_copies_source(policy: Policy) -> None:
    html: Final = "<a" + "".join(f' bad-{index}="x"' for index in range(32)) + ' href="/safe">x</a>'
    source: Final = parse_fragment(html)
    sanitized: Final = Sanitizer(policy).sanitize_node(source)
    assert (source.inner_html, sanitized.inner_html) == (html, '<a href="/safe">x</a>')


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        pytest.param(0, "<p>x</p>", id="rejected"),
        pytest.param(1, "<p" + "".join(f' data-{index}="x"' for index in range(1_024)) + ">x</p>", id="allowed"),
        pytest.param(2, '<p data-a="x" data-b="x" data-c="x" data-d="x">x</p>', id="tiny"),
    ],
)
def test_sanitize_attribute_benchmark(case: int, expected: str) -> None:
    sanitizer: Final = Sanitizer(Policy(tags=frozenset({"p"}), attribute_prefixes=frozenset({"data-"})))
    assert sanitizer.sanitize(cast("str", INPUTS["sanitize-attributes"]()[case][1])) == expected
