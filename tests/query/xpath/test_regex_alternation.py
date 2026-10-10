from __future__ import annotations

import pytest

from turbohtml import parse_xml


@pytest.mark.parametrize("repetitions", [pytest.param(1, id="single-search"), pytest.param(2, id="reused-pattern")])
@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        pytest.param("article|post", "grid post-body", True, id="later-start"),
        pytest.param("article|post", "grid content", False, id="miss"),
        pytest.param("article|post", "", False, id="empty-input"),
        pytest.param("é|post", "grid é", True, id="unicode-start"),
        pytest.param("é|post", "grid", False, id="ascii-before-unicode"),
        pytest.param("\\x7f|post", "grid\x7f", True, id="last-ascii-bit"),
        pytest.param("(?i:İ|post)", "i", True, id="unicode-fold-to-ascii"),
        pytest.param("^article|post$", "article body", True, id="start-assertion"),
        pytest.param("^article|post$", "xarticle body", False, id="failed-start-assertion"),
        pytest.param("^article|post$", "grid post", True, id="end-assertion"),
        pytest.param("^article|post$", "grid posts", False, id="failed-end-assertion"),
        pytest.param("(?:a|.)z", "éz", True, id="wildcard-unicode"),
        pytest.param("(?:a|.)z", "\nz", False, id="wildcard-newline"),
        pytest.param("(?:a|(?s:.))z", "\nz", True, id="dotall-newline"),
        pytest.param("(?:a?)*|post", "", True, id="nullable-loop"),
        pytest.param("(?:a|b)*z", "abz", True, id="loop-before-literal"),
        pytest.param("(?:a|b)*z", "abc", False, id="loop-miss"),
        pytest.param("(a|b)\\1", "bb", True, id="backreference"),
        pytest.param("(?:a?)?c", "x" * 64 + "c", True, id="shared-optional-exit"),
        pytest.param("(?:a?)?c", "x" * 64, False, id="long-miss"),
    ],
)
def test_alternation_start(pattern: str, text: str, repetitions: int, *, expected: bool) -> None:
    assert parse_xml("<r>" + "<item/>" * repetitions + "</r>").xpath(
        "count(//item[re:test($text, $pattern)])", text=text, pattern=pattern
    ) == (repetitions if expected else 0)


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        pytest.param("(art|article)", "x <art>icle <art>", id="first-shorter"),
        pytest.param("(article|art)", "x <article> <art>", id="first-longer"),
        pytest.param("(article|art)+", "x <article> <art>", id="repeated-capture"),
    ],
)
def test_alternation_capture_priority(pattern: str, expected: str) -> None:
    assert parse_xml("<r/>").xpath("re:replace('x article art', $pattern, 'g', '<\\1>')", pattern=pattern) == expected


@pytest.mark.parametrize(
    ("patterns", "flags", "expected"),
    [
        pytest.param(("a", "b", "a", "b"), ("i", "i", "i", "i"), ["0", "2"], id="changing-pattern"),
        pytest.param(("a", "a", "a", "a"), ("i", "", "i", ""), ["0", "2"], id="changing-flags"),
        pytest.param(("a", "aa", "aaa", "a"), ("i", "i", "i", "i"), ["0", "3"], id="changing-length"),
    ],
)
def test_regex_patterns_within_query(patterns: tuple[str, ...], flags: tuple[str, ...], expected: list[str]) -> None:
    assert (
        parse_xml(
            "<r>"
            + "".join(
                f'<item id="{index}" pattern="{pattern}" flags="{flag}"/>'
                for index, (pattern, flag) in enumerate(zip(patterns, flags, strict=True))
            )
            + "</r>"
        ).xpath("//item[re:test('A', @pattern, @flags)]/@id")
        == expected
    )
