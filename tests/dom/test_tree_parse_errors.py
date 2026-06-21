"""Collecting and reporting WHATWG parse errors from parse(), with optional strict mode."""

from __future__ import annotations

import gc

import pytest

from turbohtml import Document, HTMLParseError, ParseError, parse, tokenize


@pytest.mark.parametrize(
    ("markup", "code", "line", "col"),
    [
        pytest.param("<div", "eof-in-tag", 1, 4, id="eof-in-tag"),
        pytest.param("<div foo", "eof-in-tag", 1, 8, id="eof-in-tag-attr"),
        pytest.param("<!--unclosed", "eof-in-comment", 1, 12, id="eof-in-comment"),
        pytest.param("<!DOCTYPE", "eof-in-doctype", 1, 9, id="eof-in-doctype"),
        pytest.param("<a b b>", "duplicate-attribute", 1, 6, id="duplicate-attribute"),
        pytest.param("<!-->", "abrupt-closing-of-empty-comment", 1, 4, id="abrupt-empty-comment"),
        pytest.param("<!--->", "abrupt-closing-of-empty-comment", 1, 5, id="abrupt-empty-comment-dash"),
        pytest.param("</>", "missing-end-tag-name", 1, 2, id="missing-end-tag-name"),
        pytest.param("<?php?>", "unexpected-question-mark-instead-of-tag-name", 1, 1, id="question-mark"),
        pytest.param("<html><!DOCTYPE html>", "unexpected-doctype", 1, 6, id="unexpected-doctype"),
    ],
)
def test_single_error(markup: str, code: str, line: int, col: int) -> None:
    errors = parse(markup).errors
    assert len(errors) == 1
    assert (errors[0].code, errors[0].line, errors[0].col) == (code, line, col)


def test_well_formed_document_has_no_errors() -> None:
    assert parse("<!DOCTYPE html><html><body><p>hi</p></body></html>").errors == []


def test_errors_is_a_fresh_list_each_call() -> None:
    document = parse("<div")
    first = document.errors
    second = document.errors
    assert first == second
    assert first is not second  # a new list is materialized per access


def test_error_field_types() -> None:
    error = parse("<div").errors[0]
    assert isinstance(error.code, str)
    assert isinstance(error.line, int)
    assert isinstance(error.col, int)


def test_error_position_tracks_newlines() -> None:
    error = parse("\n\n<div").errors[0]  # the open tag starts on the third line
    assert error.code == "eof-in-tag"
    assert error.line == 3


def test_multiple_errors_in_document_order() -> None:
    codes = [error.code for error in parse("<a b b><c d d>").errors]
    assert codes == ["duplicate-attribute", "duplicate-attribute"]


def test_bytes_input_collects_errors() -> None:
    assert parse(b"<div").errors[0].code == "eof-in-tag"


def test_collects_more_errors_than_the_initial_capacity() -> None:
    # one unique attribute then eleven duplicates, growing the sink past its
    # initial capacity so every duplicate is still recorded
    document = parse("<a" + " b" * 12 + ">")
    assert len(document.errors) == 11
    assert {error.code for error in document.errors} == {"duplicate-attribute"}


def test_repr_round_trips_fields() -> None:
    error = parse("<div").errors[0]
    assert repr(error) == f"ParseError(code='eof-in-tag', line={error.line}, col={error.col})"


def test_equality_and_hash() -> None:
    one = parse("<div").errors[0]
    same = parse("<div").errors[0]
    other = parse("<!--x").errors[0]
    assert one == same
    assert hash(one) == hash(same)
    assert one != other
    assert one != "not a parse error"  # a foreign type compares unequal, never raising


def test_equality_compares_code_and_position() -> None:
    eof_tag = parse("<div").errors[0]  # eof-in-tag at (1, 4)
    abrupt = parse("<!-->").errors[0]  # abrupt-closing-of-empty-comment, also at (1, 4)
    next_line = parse("\n<div").errors[0]  # eof-in-tag at (2, 4): same code and column, later line
    assert eof_tag != abrupt  # same position, different code
    assert eof_tag != next_line  # same code and column, different line
    assert eof_tag == parse("<div").errors[0]  # every field matches


def test_ordering_is_unsupported() -> None:
    one = parse("<div").errors[0]
    other = parse("<!--x").errors[0]
    with pytest.raises(TypeError):
        _ = one < other  # ty: ignore[unsupported-operator]  # only equality is defined, never an ordering


def test_cannot_instantiate_parse_error() -> None:
    with pytest.raises(TypeError):
        ParseError()  # type: ignore[call-arg]


def test_strict_raises_on_first_error() -> None:
    with pytest.raises(HTMLParseError) as raised:
        parse("<div", strict=True)
    error = raised.value.error
    assert isinstance(error, ParseError)
    assert error.code == "eof-in-tag"
    assert str(raised.value) == f"eof-in-tag at line {error.line}, column {error.col}"


def test_strict_reports_only_the_first_error() -> None:
    with pytest.raises(HTMLParseError) as raised:
        parse("<a b b><c d d>", strict=True)
    assert raised.value.error.code == "duplicate-attribute"
    assert raised.value.error.col == 6  # the first duplicate, not the second


def test_strict_on_bytes_input() -> None:
    with pytest.raises(HTMLParseError) as raised:
        parse(b"<!DOCTYPE", strict=True)
    assert raised.value.error.code == "eof-in-doctype"


def test_strict_on_well_formed_input_returns_document() -> None:
    document = parse("<!DOCTYPE html><p>ok</p>", strict=True)
    assert isinstance(document, Document)
    assert document.errors == []


def test_standalone_tokenizer_ignores_errors() -> None:
    # tokenize() runs the state machine with no error sink, so a malformed run
    # still tokenizes (the duplicate attribute is dropped) without collecting.
    tokens = list(tokenize("<a b b>"))
    start = next(token for token in tokens if token.tag == "a")
    assert start.attrs == [("b", "")]  # the second b is dropped, first wins


def test_html_parse_error_is_an_exception() -> None:
    assert issubclass(HTMLParseError, Exception)


def test_parse_error_outlives_its_document() -> None:
    # a ParseError holds no reference into the tree (its code is a static string),
    # so it keeps working after the Document and its arena are collected
    error = parse("<div").errors[0]
    gc.collect()
    assert (error.code, error.line, error.col) == ("eof-in-tag", 1, 4)
    assert repr(error) == "ParseError(code='eof-in-tag', line=1, col=4)"
