from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from fuzz.atheris_content_targets import (
    content_targets,
    detector_check,
    minifier_check,
    minifier_observation,
    sanitizer_check,
    sanitizer_observation,
    stdlib_check,
    stdlib_observation,
    url_check,
)
from fuzz.atheris_header import Header

from turbohtml.clean import Removed
from turbohtml.detect import EncodingDetector
from turbohtml.migration.stdlib import HTMLParser

if TYPE_CHECKING:
    from collections.abc import Callable

    from fuzz.atheris_registry import Target
    from pytest_mock import MockerFixture

_TARGETS: Final = content_targets()


@pytest.mark.parametrize("target", _TARGETS, ids=lambda target: target.name)
@pytest.mark.parametrize("data", [b"", b"hello", bytes(range(256))], ids=["empty", "ascii", "byte-range"])
def test_content_target_behaviors(target: Target, data: bytes) -> None:
    target.callback(data)


def test_content_targets_have_unique_owners() -> None:
    exports: Final = [export for target in _TARGETS for export in target.exports]
    assert len(exports) == len(set(exports)) == 90


def test_content_sanitizer_removes_attributes_and_comments() -> None:
    assert sanitizer_observation(b"x") == (
        "<b>value78</b><b>value78</b>",
        [Removed("b", "title"), Removed("b", "onclick")],
    )


def test_content_minifiers_transform_source() -> None:
    assert minifier_observation(b"x") == (
        "<html><head></head><body><p>value78</p></body></html>",
        ".value78{color:red}",
        "color:red",
        'const value="value78"',
    )


def test_content_stdlib_decodes_chunked_references() -> None:
    assert stdlib_observation(b"x") == "value78&"


def test_content_sanitizer_rejects_wrong_renderer_result() -> None:
    def render(data: bytes) -> tuple[str, list[Removed]]:
        return data.decode(), []

    with pytest.raises(AssertionError, match="Content API mismatch"):
        sanitizer_check(b"wrong", render)


@pytest.mark.parametrize("kind", ["css-semantics", "css-fixpoint", "js-fixpoint"])
def test_content_minifier_rejects_wrong_output(kind: str) -> None:
    def wrong(source: str) -> str:
        return "q{color:blue}" if kind == "css-semantics" else source + "x"

    with pytest.raises(AssertionError, match="Content API mismatch"):
        minifier_check(b"x", js=wrong) if kind == "js-fixpoint" else minifier_check(b"x", css=wrong)


def test_content_url_rejects_stable_wrong_host() -> None:
    with pytest.raises(AssertionError, match="Content API mismatch"):
        url_check(b"x", lambda _source: "https://wrong.example/")


@pytest.mark.parametrize(
    "max_chunk", [pytest.param(1, id="one"), pytest.param(3, id="three"), pytest.param(64, id="whole")]
)
@pytest.mark.parametrize(
    ("check", "data"),
    [
        pytest.param(detector_check, "\ufeff<p>水😀</p>".encode(), id="encoding-detector"),
        pytest.param(stdlib_check, "<b>水😀&amp;</b>".encode(), id="stdlib-parser"),
    ],
)
def test_content_chunks_match_one_call(check: Callable[[bytes, Header], None], data: bytes, max_chunk: int) -> None:
    check(data, Header(0, 0, max_chunk))


@pytest.mark.parametrize(
    ("check", "consumer", "data"),
    [
        pytest.param(detector_check, EncodingDetector, "\ufeff<p>水😀</p>".encode(), id="encoding-detector"),
        pytest.param(stdlib_check, HTMLParser, "<b>水😀&amp;</b>".encode(), id="stdlib-parser"),
    ],
)
def test_content_chunks_reject_dropped_chunk(
    mocker: MockerFixture,
    check: Callable[[bytes, Header], None],
    consumer: type[EncodingDetector | HTMLParser],
    data: bytes,
) -> None:
    feed = consumer.feed
    mocker.patch.object(
        consumer, "feed", autospec=True, side_effect=lambda stream, chunk: len(chunk) == 1 or feed(stream, chunk)
    )
    with pytest.raises(AssertionError, match="Content API mismatch"):
        check(data, Header(0, 0, 1))


def test_content_url_rejects_unstable_reparse() -> None:
    with pytest.raises(AssertionError, match="reparse changes normalized URL"):
        url_check(b"x", lambda source: source + "/")
