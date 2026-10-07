from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from types import ModuleType


@pytest.fixture
def engines() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType]:
    return (
        pytest.importorskip("fuzz.schema_mutation", exc_type=ImportError),
        pytest.importorskip("fuzz.xslt_inline", exc_type=ImportError),
        pytest.importorskip("fuzz.xsd_inline", exc_type=ImportError),
        pytest.importorskip("fuzz.rng_inline", exc_type=ImportError),
        pytest.importorskip("lxml.etree", exc_type=ImportError),
    )


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("index", "count"),
    [pytest.param(1, 10, id="xslt"), pytest.param(2, 6, id="xsd"), pytest.param(3, 6, id="rng")],
)
@pytest.mark.parametrize("broken", [False, True], ids=["repaired", "broken"])
def test_schema_mutation_registered_cli(
    engines: tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType],
    capsys: pytest.CaptureFixture[str],
    index: int,
    count: int,
    *,
    broken: bool,
) -> None:
    arguments = ["--cases", str(count), "--mutate"]
    if broken:
        arguments.append("--broken-references")
    assert engines[index].main(arguments) == 0
    assert '"findings": 0' in capsys.readouterr().out


@pytest.mark.oracle
def test_schema_mutation_xpath_literals_and_declarations(
    engines: tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    root: Final = (
        '<x:stylesheet xmlns:x="http://www.w3.org/1999/XSL/Transform" version="1.0">'
        '<x:output method="text"/><x:variable name="recipient" select="&apos;kept&apos;"/>'
        '<x:key name="recipient-key" match="item" use="@id"/>'
        '<x:template name="recipient-template">template</x:template>'
        '<x:template match="/"/></x:stylesheet>'
    )
    donor: Final = root.replace("recipient", "donor").replace(
        '<x:template match="/"/>',
        """<x:template match="/"><x:value-of select="concat('$literal', $donor, key('donor-key', 'one'))"/>
        <x:call-template name="donor-template"/></x:template>""",
    )
    mutated: Final = engines[0].mutate(root, (donor,), 0)
    assert str(engines[4].XSLT(engines[4].fromstring(mutated.encode()))(engines[4].fromstring(b"<root/>"))) == (
        "$literalkepttemplate"
    )


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("source", "message"),
    [
        pytest.param("<root/>", "only inline", id="unsupported"),
        pytest.param(
            '<x:stylesheet xmlns:x="http://www.w3.org/1999/XSL/Transform"/>',
            "root template",
            id="missing-template",
        ),
        pytest.param(
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>',
            "global element",
            id="missing-element",
        ),
        pytest.param(
            '<rng:grammar xmlns:rng="http://relaxng.org/ns/structure/1.0"/>',
            "start pattern",
            id="missing-start",
        ),
    ],
)
def test_schema_mutation_rejects_missing_seed_contract(
    engines: tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType],
    source: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        engines[0].mutate(source, (source,), 0)


@pytest.mark.oracle
@pytest.mark.parametrize("index", [2, 3], ids=["xsd", "rng"])
def test_schema_mutation_cli_requires_mutation_for_broken_references(
    engines: tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType],
    index: int,
) -> None:
    with pytest.raises(SystemExit, match="2"):
        engines[index].main(["--broken-references"])


@pytest.mark.oracle
def test_schema_mutation_rng_missing_recipient_definition_is_not_invented(
    engines: tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType],
) -> None:
    source: Final = (
        '<rng:grammar xmlns:rng="http://relaxng.org/ns/structure/1.0">'
        '<rng:start><rng:element name="v"><rng:empty/></rng:element></rng:start></rng:grammar>'
    )
    mutated: Final = engines[0].mutate(source, (engines[3].generate(0).schema,), 0)
    case: Final = engines[3].Case(0, mutated, compiles=False, documents=())
    assert [(row.engine, row.expected, row.actual) for row in engines[3].compare(case)] == [
        ("turbohtml", False, False),
        ("libxml2", False, False),
    ]


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("index", "source"),
    [
        pytest.param(
            1,
            '<x:stylesheet version="1.0"><x:output method="text"/>'
            '<x:template match="/">word</x:template></x:stylesheet>',
            id="x",
        ),
        pytest.param(2, '<xs:schema><xs:element name="v" type="xs:string"/></xs:schema>', id="xs"),
        pytest.param(
            3,
            '<rng:grammar><rng:start><rng:element name="v"><rng:empty/></rng:element></rng:start></rng:grammar>',
            id="rng",
        ),
    ],
)
def test_schema_mutation_binds_dictionary_prefixes(
    engines: tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType],
    index: int,
    source: str,
) -> None:
    mutated: Final = engines[0].mutate(source, (source,), 0)
    reference: Final = engines[4].fromstring(mutated.encode())
    if index == 1:
        assert str(engines[4].XSLT(reference)(engines[4].fromstring(b"<root/>"))) == "word"
    else:
        validator: Final = engines[4].XMLSchema(reference) if index == 2 else engines[4].RelaxNG(reference)
        assert validator.validate(engines[4].fromstring(b"<v/>"))


@pytest.mark.oracle
@pytest.mark.parametrize("source", ["", "<root/><root/>"], ids=["empty", "multiple"])
def test_schema_mutation_requires_one_dictionary_root(
    engines: tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType],
    source: str,
) -> None:
    with pytest.raises(ValueError, match="one root element"):
        engines[0].mutate(source, (source,), 0)
