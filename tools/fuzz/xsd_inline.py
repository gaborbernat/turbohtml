"""Inline labels retain compiler errors alongside document verdicts."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Final

import lxml.etree

from turbohtml import parse_xml
from turbohtml.validate import XMLSchema

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

__all__: Final = ["Case", "Verdict", "compare", "generate", "main"]

_XS: Final = 'xmlns:xs="http://www.w3.org/2001/XMLSchema"'


def main(argv: Sequence[str] | None = None) -> int:
    """Keep compiler and validation findings in the exit status."""
    parser: Final = argparse.ArgumentParser(description="Compare bounded inline XSD schemas with libxml2.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cases", type=int, default=32)
    parser.add_argument("--negative-control", action="store_true")
    arguments: Final = parser.parse_args(argv)
    if not 1 <= arguments.cases <= 256:
        parser.error("--cases must be between 1 and 256")
    findings = 0
    rows = 0
    for seed in range(arguments.seed, arguments.seed + arguments.cases):
        for verdict in compare(generate(seed), negative_control=arguments.negative_control):
            findings += verdict.actual != verdict.expected
            rows += 1
            print(json.dumps(asdict(verdict), sort_keys=True))
    print(json.dumps({"summary": {"cases": arguments.cases, "rows": rows, "findings": findings}}, sort_keys=True))
    return int(findings != 0)


def compare(case: Case, *, negative_control: bool = False) -> Iterator[Verdict]:
    """Compile first so invalid schemas remain part of the comparison."""
    schema_hash: Final = hashlib.sha256(case.schema.encode()).hexdigest()
    ours: Final = _compile_turbohtml(case.schema)
    reference: Final = _compile_lxml(case.schema)
    yield Verdict(case.seed, schema_hash, "turbohtml", "compilation", case.compiles, ours is not None)
    yield Verdict(case.seed, schema_hash, "libxml2", "compilation", case.compiles, reference is not None)
    for document, expected in case.documents:
        document_hash: Final = hashlib.sha256((case.schema + "\\0" + document).encode()).hexdigest()
        actual: Final = None if ours is None else ours.is_valid(parse_xml(document))
        yield Verdict(
            case.seed,
            document_hash,
            "turbohtml",
            "validation",
            expected,
            not actual if negative_control and actual is not None else actual,
        )
        yield Verdict(
            case.seed,
            document_hash,
            "libxml2",
            "validation",
            expected,
            None if reference is None else reference.validate(lxml.etree.fromstring(document.encode(), _parser())),
        )


def generate(seed: int) -> Case:
    """Known labels distinguish shared mistakes from agreement."""
    rng: Final = random.Random(seed)
    number: Final = rng.randrange(1, 100)
    word: Final = f"word{number}"
    family: Final = seed % 8
    if family == 0:
        declarations: Final = '<xs:element name="v" type="xs:string"/>'
        documents: Final = ((f"<v>{word}</v>", True), ("<v/>", True), ("<other/>", False))
    elif family == 1:
        declarations = '<xs:element name="v" type="xs:integer"/>'
        documents = ((f"<v>{number}</v>", True), ("<v>wrong</v>", False), ("<other/>", False))
    elif family == 2:
        declarations = (
            '<xs:element name="v"><xs:simpleType><xs:restriction base="xs:token">'
            f'<xs:enumeration value="{word}"/></xs:restriction></xs:simpleType></xs:element>'
        )
        documents = ((f"<v>  {word}  </v>", True), ("<v>wrong</v>", False), ("<other/>", False))
    elif family == 3:
        declarations = (
            '<xs:element name="v"><xs:complexType><xs:sequence><xs:element name="child" type="xs:integer"/>'
            "</xs:sequence></xs:complexType></xs:element>"
        )
        documents = ((f"<v><child>{number}</child></v>", True), ("<v/>", False), ("<other/>", False))
    elif family == 4:
        declarations = (
            '<xs:element name="v"><xs:complexType><xs:attribute name="key" type="xs:integer" use="required"/>'
            "</xs:complexType></xs:element>"
        )
        documents = ((f'<v key="{number}"/>', True), ('<v key="wrong"/>', False), ("<v/>", False))
    elif family == 5:
        declarations = (
            '<xs:element name="v"><xs:simpleType><xs:restriction base="xs:integer">'
            f'<xs:minInclusive value="{number}"/><xs:maxInclusive value="{number + 2}"/>'
            "</xs:restriction></xs:simpleType></xs:element>"
        )
        documents = ((f"<v>{number}</v>", True), (f"<v>{number + 3}</v>", False), ("<v>wrong</v>", False))
    else:
        declarations = '<xs:element name="v" type="xs:notAType"/>' if family == 6 else '<xs:element type="xs:string"/>'
        documents = ()
    return Case(seed, f"<xs:schema {_XS}>{declarations}</xs:schema>", family < 6, documents)


def _compile_turbohtml(schema: str) -> XMLSchema | None:
    try:
        return XMLSchema(schema)
    except ValueError:
        return None


def _compile_lxml(schema: str) -> lxml.etree.XMLSchema | None:
    try:
        return lxml.etree.XMLSchema(lxml.etree.fromstring(schema.encode(), _parser()))
    except (lxml.etree.XMLSchemaParseError, lxml.etree.XMLSyntaxError):
        return None


def _parser() -> lxml.etree.XMLParser:
    return lxml.etree.XMLParser(resolve_entities=False, no_network=True)


@dataclass(frozen=True)
class Case:
    """Expected labels retain shared compiler errors."""

    seed: int
    schema: str
    compiles: bool
    documents: tuple[tuple[str, bool], ...]


@dataclass(frozen=True)
class Verdict:
    """Unavailable document results keep compilation failures visible."""

    seed: int
    sha256: str
    engine: str
    phase: str
    expected: bool
    actual: bool | None


if __name__ == "__main__":
    raise SystemExit(main())
