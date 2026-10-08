from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from fuzz.atheris_reference_targets import (
    cli_observation,
    computed_observation,
    conformance_observation,
    cssom_observation,
    reference_targets,
    render_observation,
    schema_observation,
    selector_observation,
    transform_observation,
)

from turbohtml import HTMLParseError
from turbohtml.convert import ExpressionError

if TYPE_CHECKING:
    from collections.abc import Callable

    from fuzz.atheris_registry import Target


def test_atheris_reference_rendered_text() -> None:
    assert render_observation(b"<p>one <b>two</b></p>") == (
        "one **two**",
        "one two",
        "one two",
        b"<html><head></head><body><p>one <b>two</b></p></body></html>",
    )


def test_atheris_reference_annotation_text() -> None:
    markdown, plain, tagged, canonical = render_observation(b'<p><a href="/x">one</a></p>')
    assert (markdown, plain, tagged, canonical) == (
        "[one](/x)",
        "one",
        "<link>one</link>",
        b'<html><head></head><body><p><a href="/x">one</a></p></body></html>',
    )


def test_atheris_reference_conformance_records() -> None:
    valid, codes, diagnostic = conformance_observation(
        b'<html lang="en"><head><title>x</title></head><body><img></body></html>'
    )
    assert (valid, "img-missing-alt" in codes, diagnostic) == (False, True, None)


def test_atheris_reference_css_records() -> None:
    assert cssom_observation(b"color:red;color:blue!important;margin:0") == (
        ("color", "blue", True),
        ("margin", "0", False),
    )


def test_atheris_reference_empty_css_records() -> None:
    assert cssom_observation(b"") == ()


def test_atheris_reference_selector_specificity() -> None:
    expression, specificity = selector_observation(b"div#a > p.x")
    assert (bool(expression), specificity) == (True, ((1, 1, 2),))


def test_atheris_reference_untranslatable_selector() -> None:
    with pytest.raises(ExpressionError):
        selector_observation(b":dir(ltr)")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(b"<root>one</root>", (True, True), id="valid"),
        pytest.param(b"<wrong/>", (False, False), id="invalid"),
    ],
)
def test_atheris_reference_schema_verdict(source: bytes, expected: tuple[bool, bool]) -> None:
    assert schema_observation(source) == expected


@pytest.mark.parametrize(
    "source",
    [pytest.param(b"one", id="plain"), pytest.param(b"\x00", id="null"), pytest.param(b"""a'b"c""", id="both-quotes")],
)
def test_atheris_reference_transform_parameter(source: bytes) -> None:
    assert transform_observation(source) == source.decode()


def test_atheris_reference_cli_file_output() -> None:
    assert cli_observation(b"<p>one<br>two</p>") == "one\ntwo"


@pytest.mark.parametrize("target", reference_targets(), ids=lambda target: target.name)
def test_atheris_reference_callback_rejects_invalid_utf8(target: Target) -> None:
    with pytest.raises(UnicodeDecodeError):
        target.callback(b"\xff")


def test_atheris_reference_strict_parse_record() -> None:
    assert conformance_observation(b"<div")[2] == ("eof-in-tag", 1, 4)


@pytest.mark.parametrize(
    ("source", "expected"),
    [pytest.param(b"color:blue!important", "blue", id="declared"), pytest.param(b"", "black", id="fallback")],
)
def test_atheris_reference_computed_cascade(source: bytes, expected: str) -> None:
    assert computed_observation(source) == expected


def test_atheris_reference_xml_rejection_is_documented() -> None:
    target: Final = next(target for target in reference_targets() if target.name == "xml-schema")
    assert target.exceptions == (UnicodeDecodeError, HTMLParseError)
    with pytest.raises(HTMLParseError):
        target.callback(b"<root>")


@pytest.mark.parametrize(
    ("observe", "oracle", "data"),
    [
        pytest.param(schema_observation, "xml", b"<root>text</root>", id="xml-fixpoint"),
        pytest.param(cssom_observation, "style", b"color: red", id="style-fixpoint"),
        pytest.param(selector_observation, "entries", b"p.x", id="selector-entries"),
    ],
)
def test_reference_reports_oracle_failure(observe: Callable[..., object], oracle: str, data: bytes) -> None:
    with pytest.raises(AssertionError, match=r"^oracle broke$"):
        observe(data, **{oracle: lambda _text: "oracle broke"})
