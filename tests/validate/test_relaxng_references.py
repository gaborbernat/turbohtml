from __future__ import annotations

from typing import Final

import pytest

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG

_NAMESPACE: Final = 'xmlns="http://relaxng.org/ns/structure/1.0"'


@pytest.mark.parametrize("count", [0, 1, 12], ids=["empty", "linear", "hashed"])
@pytest.mark.parametrize(
    "pattern",
    [
        pytest.param('<ref name="missing"/>', id="start"),
        pytest.param('<element name="root"><ref name="missing"/></element>', id="element"),
        pytest.param(
            '<element name="root"><interleave><ref name="missing"/><empty/></interleave></element>', id="interleave"
        ),
    ],
)
def test_relaxng_undefined_reference_rejects_compilation(count: int, pattern: str) -> None:
    definitions: Final = "".join(f'<define name="entry{index}"><empty/></define>' for index in range(count))
    schema: Final = f"<grammar {_NAMESPACE}><start>{pattern}</start>{definitions}</grammar>"
    for _ in range(2):
        with pytest.raises(ValueError, match="has no matching define"):
            RelaxNG(schema)


def test_relaxng_undefined_short_reference_rejects_compilation() -> None:
    for _ in range(2):
        with pytest.raises(ValueError, match="has no matching define"):
            RelaxNG(f'<element {_NAMESPACE} name="root"><ref name="missing"/></element>')


@pytest.mark.parametrize("count", [0, 12], ids=["linear", "hashed"])
def test_relaxng_forward_reference_preserves_recursive_validation(count: int) -> None:
    definitions: Final = "".join(f'<define name="unused{index}"><empty/></define>' for index in range(count))
    schema: Final = (
        f'<grammar {_NAMESPACE}><start><ref name="entry"/></start>'
        '<define name="entry"><element name="root"><optional><ref name="entry"/></optional></element></define>'
        f"{definitions}</grammar>"
    )
    validator: Final = RelaxNG(schema)
    assert [
        [validator.is_valid(parse_xml(document)) for document in ("<root/>", "<root><root/></root>", "<wrong/>")]
        for _ in range(2)
    ] == [[True, True, False], [True, True, False]]


@pytest.mark.parametrize(
    "pattern",
    [
        pytest.param('<ref name="missing"/>', id="unknown"),
        pytest.param("<ref/>", id="absent-name"),
        pytest.param('<element name="dead"><ref name="missing"/></element>', id="nested"),
    ],
)
def test_relaxng_undefined_unused_reference_rejects_compilation(pattern: str) -> None:
    schema: Final = (
        f'<grammar {_NAMESPACE}><start><element name="root"><empty/></element></start>'
        f'<define name="unused">{pattern}</define></grammar>'
    )
    with pytest.raises(ValueError, match="RELAX NG <ref>"):
        RelaxNG(schema)


@pytest.mark.parametrize(
    "definitions",
    [
        pytest.param(
            '<define name="unused"><!--annotation--><ref name="unused"/></define>',
            id="unused-cycle",
        ),
        pytest.param(
            '<define name="unused" combine="choice"><empty/></define>'
            '<define name="unused" combine="choice"><ref name="unused"/></define>',
            id="combined-unused-cycle",
        ),
    ],
)
def test_relaxng_unused_reference_cycle_preserves_reachable_validation(definitions: str) -> None:
    schema: Final = (
        f'<grammar {_NAMESPACE}><start><element name="root"><empty/></element></start>{definitions}</grammar>'
    )
    validator: Final = RelaxNG(schema)
    assert [validator.is_valid(parse_xml(document)) for document in ("<root/>", "<other/>")] == [True, False]


def test_relaxng_undefined_combined_unused_reference_rejects_compilation() -> None:
    schema: Final = (
        f'<grammar {_NAMESPACE}><start><element name="root"><empty/></element></start>'
        '<define name="unused" combine="choice"><empty/></define>'
        '<define name="unused" combine="choice"><ref name="missing"/></define></grammar>'
    )
    with pytest.raises(ValueError, match="has no matching define"):
        RelaxNG(schema)


def test_relaxng_unused_foreign_annotation_is_ignored() -> None:
    schema: Final = (
        f'<grammar {_NAMESPACE} xmlns:doc="urn:documentation">'
        '<start><element name="root"><empty/></element></start>'
        '<define name="unused"><doc:annotation><ref name="missing"/></doc:annotation><empty/></define></grammar>'
    )
    assert RelaxNG(schema).is_valid(parse_xml("<root/>"))


def test_relaxng_annotation_normalization_preserves_public_source() -> None:
    source: Final = parse_xml(
        f'<element {_NAMESPACE} xmlns:doc="urn:documentation" name="root">'
        '<empty/><doc:annotation><ref name="missing"/></doc:annotation></element>'
    )
    serialized: Final = source.serialize()
    validator: Final = RelaxNG(source)
    assert (source.serialize(), validator.is_valid(parse_xml("<root/>"))) == (serialized, True)
