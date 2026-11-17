from __future__ import annotations

import itertools
import random
import string
from typing import TYPE_CHECKING, Final

import pytest

import turbohtml
from turbohtml.clean import minify_css, minify_js
from turbohtml.transform import Transform
from turbohtml.validate import RelaxNG, XMLSchema

if TYPE_CHECKING:
    from collections.abc import Callable

    from work_steps import WorkSteps

_LOW: Final[int] = 0xFFFF
_FNV32: Final[tuple[int, int]] = (2166136261, 16777619)
_FNV64: Final[tuple[int, int]] = (14695981039346656037, 1099511628211)
_XSLT64: Final[tuple[int, int]] = (1469598103934665603, 1099511628211)  # the basis xslt.c's str_hash starts from
_STEPS: Final[int] = 10
_FACTOR: Final[float] = 16.0
_LINED_UP: Final[int] = 512
_TRANSLATE_FROM: Final[int] = 512
_TRANSLATE_CAPACITY: Final[int] = 1024  # th_grow_cap(2 * 512) slots, the stride that puts every from character home
_TRANSLATE_MULTIPLIER: Final[int] = 2654435761  # the multiplicative hash of translate() in xpath/functions.c


def _attribute_tag(names: list[str]) -> str:
    return f"<i {' '.join(names)}>"


def _tokenize(names: list[str]) -> Callable[[], object]:
    return lambda: list(turbohtml.tokenize(_attribute_tag(names)))


def _parse(names: list[str]) -> Callable[[], object]:
    return lambda: turbohtml.parse(_attribute_tag(names))


def _css_declarations(names: list[str]) -> Callable[[], object]:
    return lambda: minify_css(f"p{{{';'.join(f'{name}:1' for name in names)}}}")


def _xpath_id(names: list[str]) -> Callable[[], object]:
    document: Final = turbohtml.parse(
        f'<input aria-labelledby="{" ".join(names)}">{"".join(f"<p id={name}>" for name in names)}'
    )
    return lambda: document.xpath("id(//input/@aria-labelledby)")


def _xsl_key(names: list[str]) -> Callable[[], object]:
    source: Final = turbohtml.parse_xml("<items>{}</items>".format("".join(f'<item id="{name}"/>' for name in names)))
    transform: Final = Transform(
        turbohtml.parse_xml(
            '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
            '<xsl:output method="text"/><xsl:key name="by-id" match="item" use="@id"/>'
            '<xsl:template match="/"><xsl:value-of select="count(key(\'by-id\', //item/@id))"/></xsl:template>'
            "</xsl:stylesheet>"
        ),
        allow_imports=False,
    )
    return lambda: transform(source)


def _xsl_attribute_sets(names: list[str]) -> Callable[[], object]:
    sets: Final = "".join(f'<xsl:attribute-set name="{name}"/>' for name in names)
    uses: Final = " ".join(names)
    sheet: Final = turbohtml.parse_xml(
        f'<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">{sets}'
        f'<xsl:template match="/"><r xsl:use-attribute-sets="{uses}"/></xsl:template></xsl:stylesheet>'
    )
    source: Final = turbohtml.parse_xml("<r/>")
    return lambda: Transform(sheet, allow_imports=False)(source)


def _xsl_key_names(names: list[str]) -> Callable[[], object]:
    keys: Final = "".join(f'<xsl:key name="{name}" match="item" use="@id"/>' for name in names)
    sheet: Final = turbohtml.parse_xml(
        '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
        f'<xsl:output method="text"/>{keys}<xsl:template match="/">'
        f"<xsl:value-of select=\"count(key('{names[-1]}', 'x'))\"/></xsl:template></xsl:stylesheet>"
    )
    source: Final = turbohtml.parse_xml('<items><item id="x"/></items>')
    return lambda: Transform(sheet, allow_imports=False)(source)


def _xsl_named_templates(names: list[str]) -> Callable[[], object]:
    templates: Final = "".join(f'<xsl:template name="{name}"><xsl:text>ok</xsl:text></xsl:template>' for name in names)
    sheet: Final = turbohtml.parse_xml(
        '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
        f'<xsl:output method="text"/>{templates}<xsl:template match="/">'
        f'<xsl:call-template name="{names[-1]}"/></xsl:template></xsl:stylesheet>'
    )
    source: Final = turbohtml.parse_xml("<r/>")
    return lambda: Transform(sheet, allow_imports=False)(source)


def _minify_js_names(names: list[str]) -> Callable[[], object]:
    source: Final = f"function f(){{var {','.join(names)};return [{','.join(names)}]}}"
    return lambda: minify_js(source)


def _microdata(names: list[str]) -> Callable[[], object]:
    document: Final = turbohtml.parse(f"<div itemscope itemref=x></div>{''.join(f'<p id={name}>' for name in names)}")
    return document.microdata


def _shadow_slots(names: list[str]) -> Callable[[], object]:
    slots: Final = "".join(f"<slot name={name}></slot>" for name in names)
    document: Final = turbohtml.parse(f"<div><template shadowrootmode=open>{slots}</template><b slot=q>y</b></div>")
    return lambda: document.select("div")[0].flattened_children


def _css_path(names: list[str]) -> Callable[[], object]:
    document: Final = turbohtml.parse(f"<!doctype html>{''.join(f'<p id={name}>' for name in names)}")
    return document.select("p")[0].css_path


def _radio_group(names: list[str]) -> Callable[[], object]:
    ids: Final = "".join(f"<p id={name}>" for name in names)
    radios: Final = "".join(f"<input type=radio name=g checked form={name}>" for name in names)
    document: Final = turbohtml.parse(f"{ids}{radios}<input type=radio name=g>")
    target: Final = document.select("input")[-1]

    def check() -> None:
        target.checked = True

    return check


def _relaxng_defines(names: list[str]) -> Callable[[], object]:
    defines: Final = "".join(
        f'<define name="{name}"><element name="{name}"><empty/></element></define>' for name in names
    )
    refs: Final = "".join(f'<ref name="{name}"/>' for name in names)
    schema: Final = f'<grammar xmlns="http://relaxng.org/ns/structure/1.0"><start><choice>{refs}</choice></start>{defines}</grammar>'
    return lambda: RelaxNG(schema)


def _xsd_prefixes(names: list[str]) -> Callable[[], object]:
    declarations: Final = " ".join(f'xmlns:{name}="urn:{index}"' for index, name in enumerate(names))
    schema: Final = (
        f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" {declarations}><xs:element name="r"/></xs:schema>'
    )
    return lambda: XMLSchema(schema)


def _xsd_attributes(names: list[str]) -> Callable[[], object]:
    declared: Final = "".join(f'<xs:attribute name="{name}" type="xs:string"/>' for name in names)
    schema: Final = (
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="r"><xs:complexType>'
        f"{declared}</xs:complexType></xs:element></xs:schema>"
    )
    attributes: Final = " ".join(f'{name}="x"' for name in names)
    instance: Final = f"<r {attributes}/>"
    return lambda: XMLSchema(schema).validate(turbohtml.parse_xml(instance))


def _xpath_namespace_uris(names: list[str]) -> Callable[[], object]:
    declarations: Final = " ".join(f'xmlns:p{index}="{name}"' for index, name in enumerate(names))
    document: Final = turbohtml.parse_xml(f"<r {declarations}></r>")
    return lambda: document.xpath("//r")


def _mixed_fnv64(salt: bytes, units: list[int]) -> int:
    # The XML parser's and c14n's tables: FNV-1a from the salt's Python hash, finished with the splitmix64 mix.
    state = (hash(salt) ^ _FNV64[0]) & _MASK64
    for unit in units:
        state = ((state ^ unit) * _FNV64[1]) & _MASK64
    state = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    state = ((state ^ (state >> 27)) * 0x94D049BB133111EB) & _MASK64
    return state ^ (state >> 31)


def _c14n_prefix_slot(name: str) -> int:
    return _mixed_fnv64(b"turbohtml:c14n-prefix", list(name.encode()))


def _path_type_slot(name: str) -> int:
    # The element path cache: FNV-1a over the namespace, the atom (0 for an unknown tag) and the tag text, then the
    # Fibonacci step on the high half; a 256-slot table keeps the top eight bits.
    state = ((hash(b"turbohtml:path-type") ^ _FNV64[0]) * _FNV64[1]) & _MASK64
    state = (state * _FNV64[1]) & _MASK64
    for char in name:
        state = ((state ^ ord(char)) * _FNV64[1]) & _MASK64
    return (((state >> 32) * 0x61C88647) & 0xFFFFFFFF) >> 24


def _route_slot(name: str) -> int:
    # RELAX NG's route key of an element with no namespace: the empty URI's FNV-1a state times the golden ratio, XOR the
    # local name's FNV-1a state, folded to the low bits of a 512-slot table.
    state = ((_XSLT64[0] * 0x9E3779B97F4A7C15) & _MASK64) ^ _fnv_units(_XSLT64, [ord(char) for char in name])
    return (state ^ (state >> 32)) & 511


def _fnv_units(basis: tuple[int, int], units: list[int]) -> int:
    state = basis[0]
    for unit in units:
        state = ((state ^ unit) * basis[1]) & _MASK64
    return state


def _c14n_declarations(names: list[str]) -> Callable[[], object]:
    declarations: Final = " ".join(f'xmlns:{name}="urn:{index}"' for index, name in enumerate(names))
    document: Final = turbohtml.parse_xml(f"<r {declarations}><x/></r>")
    return document.canonicalize


def _path_type_children(names: list[str]) -> Callable[[], object]:
    # The first path on a fresh list counts only its own steps; the second resolves every sibling of the list.
    body: Final = "".join(f"<{name}></{name}>" for name in names)
    document: Final = turbohtml.parse(f"<div>{body}</div>")
    children: Final = document.select("div > *")
    return lambda: (children[0].css_path(), children[-1].css_path())


def _route_children(names: list[str]) -> Callable[[], object]:
    elements: Final = "".join(f'<element name="{name}"><empty/></element>' for name in names)
    schema: Final = (
        '<grammar xmlns="http://relaxng.org/ns/structure/1.0"><start><element name="root">'
        f"<zeroOrMore><choice>{elements}</choice></zeroOrMore></element></start></grammar>"
    )
    validator: Final = RelaxNG(schema)
    body: Final = "".join(f"<{name}/>" for name in names)
    document: Final = turbohtml.parse_xml(f"<root>{body}</root>")
    return lambda: validator.validate(document)


def _xml_prefixes(names: list[str]) -> Callable[[], object]:
    declarations: Final = " ".join(f'xmlns:{name}="urn:{index}"' for index, name in enumerate(names))
    return lambda: turbohtml.parse_xml(f"<r {declarations}/>")


_XML_SALT: Final[str] = "turbohtml:xml-attr-dup"
_MASK64: Final[int] = (1 << 64) - 1
_XSLT_FNV64_BASIS: Final[int] = 14695981039346656037


def _xml_prefix_slot(name: str) -> int:
    return _mixed_fnv64(b"turbohtml:xml-attr-dup", [ord(char) for char in name])


def _xml_expanded_attributes(names: list[str]) -> Callable[[], object]:
    attributes: Final = " ".join(f'p:{name}="1"' for name in names)
    return lambda: turbohtml.parse_xml(f'<r xmlns:p="urn:x" {attributes}/>')


def _xml_expanded_slot(name: str) -> int:
    return _mixed_fnv64(b"turbohtml:xml-attr-dup", [ord(char) for char in f"urn:x:{name}"])


@pytest.mark.parametrize(
    ("slot", "bits", "count", "build"),
    [
        pytest.param(_xml_prefix_slot, 9, 128, _xml_prefixes, id="xml-prefixes"),
        pytest.param(_xml_expanded_slot, 9, 128, _xml_expanded_attributes, id="xml-expanded-attribute-names"),
        pytest.param(_c14n_prefix_slot, 9, 256, _c14n_declarations, id="c14n-prefixes"),
        pytest.param(_path_type_slot, 8, 128, _path_type_children, id="element-path-types"),
        pytest.param(_route_slot, 9, 256, _route_children, id="relaxng-route-keys"),
    ],
)
def test_names_on_one_home_slot_under_a_mixed_hash_stay_within_the_step_budget(
    work_steps: WorkSteps,
    slot: Callable[[str], int],
    bits: int,
    count: int,
    build: Callable[[list[str]], Callable[[], object]],
) -> None:
    collide = _colliding_on_slot(slot, bits, count, 12)
    work_steps.assert_within(build(collide), build(_spread(len(collide), len(collide[0]))), factor=_FACTOR)


def _colliding_on_slot(slot: Callable[[str], int], bits: int, count: int, length: int) -> list[str]:
    # Random lowercase names kept when they share the first kept name's low `bits` slot bits, so the run stays on one
    # home until the table grows past 2 ** bits slots.
    rng: Final = random.Random(1)  # ruff: ignore[suspicious-non-cryptographic-random-usage]  # reproducible input
    mask: Final = (1 << bits) - 1
    names: list[str] = []
    home = -1
    while len(names) < count:
        name = "".join(rng.choices(string.ascii_lowercase, k=length))
        value = slot(name) & mask
        if home < 0:
            home = value
        if value == home:
            names.append(name)
    return names


def _spread(count: int, length: int) -> list[str]:
    rng: Final = random.Random(1)  # ruff: ignore[suspicious-non-cryptographic-random-usage]  # reproducible input
    return ["".join(rng.choices(string.ascii_lowercase, k=length)) for _ in range(count)]


_FNV64_PRIME: Final[int] = 1099511628211
_FNV32_BASIS: Final[int] = 2166136261
_FNV32_PRIME: Final[int] = 16777619
_THUE_MORSE_FACTOR: Final[float] = 4.0  # a quadratic probe run beside a linear build clears 4 at 256 names
_THUE_MORSE_EXPONENT: Final[int] = 12  # blocks of 2 ** 12 letters: a Thue-Morse block and its complement fold alike


def _xml_prefix_start() -> int:
    return (hash(b"turbohtml:xml-attr-dup") ^ _FNV64[0]) & _MASK64


def _c14n_prefix_start() -> int:
    return (hash(b"turbohtml:c14n-prefix") ^ _FNV64[0]) & _MASK64


def _path_type_start() -> int:
    return ((hash(b"turbohtml:path-type") ^ _FNV64[0]) * _FNV64_PRIME * _FNV64_PRIME) & _MASK64


@pytest.mark.parametrize(
    ("build", "shape"),
    [
        pytest.param(_xml_prefixes, (_xml_prefix_start(), _FNV64_PRIME, _MASK64, ""), id="xml-prefixes"),
        pytest.param(
            _xml_expanded_attributes, (_xml_prefix_start(), _FNV64_PRIME, _MASK64, "urn:x:"), id="xml-expanded"
        ),
        pytest.param(_c14n_declarations, (_c14n_prefix_start(), _FNV64_PRIME, _MASK64, ""), id="c14n-prefixes"),
        pytest.param(_path_type_children, (_path_type_start(), _FNV64_PRIME, _MASK64, ""), id="element-path-types"),
        pytest.param(_route_children, (_XSLT64[0], _XSLT64[1], _MASK64, ""), id="relaxng-route-keys"),
        pytest.param(_relaxng_defines, (_XSLT64[0], _XSLT64[1], _MASK64, ""), id="relaxng-defines"),
        pytest.param(_xsd_attributes, (_XSLT64[0], _XSLT64[1], _MASK64, ""), id="xsd-attribute-names"),
        pytest.param(_xsd_prefixes, (_XSLT64[0], _XSLT64[1], _MASK64, ""), id="xsd-namespace-prefixes"),
        pytest.param(_xpath_namespace_uris, (_FNV32_BASIS, _FNV32_PRIME, 0xFFFFFFFF, ""), id="xpath-namespace-uris"),
    ],
)
def test_thue_morse_names_stay_within_the_step_budget(
    work_steps: WorkSteps, build: Callable[[list[str]], Callable[[], object]], shape: tuple[int, int, int, str]
) -> None:
    start, prime, mask, prefix = shape
    collide = _thue_morse_names(256)
    assert _fold(start, prime, mask, prefix + collide[0]) == _fold(start, prime, mask, prefix + collide[-1])
    work_steps.assert_within(build(collide), build(_spread(len(collide), len(collide[0]))), factor=_THUE_MORSE_FACTOR)


def _thue_morse_names(count: int) -> list[str]:
    # Every name concatenates eight Thue-Morse blocks, each the block or its complement; the blocks fold alike from any
    # state at this exponent, so the names share one hash under the FNV-1a shapes the tables used before.
    word: list[int] = [0]
    for _ in range(_THUE_MORSE_EXPONENT):
        word += [1 - letter for letter in word]
    block = "".join("ab"[letter] for letter in word)
    complement = "".join("ab"[1 - letter] for letter in word)
    width = count.bit_length() - 1
    return ["".join(complement if (index >> bit) & 1 else block for bit in range(width)) for index in range(count)]


def _fold(start: int, prime: int, mask: int, text: str) -> int:
    state = start
    for char in text:
        state = ((state ^ ord(char)) * prime) & mask
    return state


def _css_rule_selectors(names: list[str]) -> Callable[[], object]:
    source: Final = "".join(f"{name}{{order:{index}}}" for index, name in enumerate(names))
    return lambda: minify_css(source)


@pytest.mark.parametrize(
    ("fnv", "build"),
    [
        pytest.param(_FNV32, _tokenize, id="tokenizer-attribute-names"),
        pytest.param(_FNV32, _parse, id="tree-attribute-names"),
        pytest.param(_FNV32, _css_declarations, id="css-declarations"),
        pytest.param(_FNV64, _xpath_id, id="xpath-id-tokens"),
        pytest.param(_XSLT64, _xsl_key, id="xsl-key-values"),
        pytest.param(_XSLT64, _xsl_attribute_sets, id="xsl-attribute-set-names"),
        pytest.param(_XSLT64, _xsl_key_names, id="xsl-key-names"),
        pytest.param(_XSLT64, _xsl_named_templates, id="xsl-template-names"),
        pytest.param(_FNV32, _minify_js_names, id="minify-js-names"),
        pytest.param(_FNV32, _microdata, id="microdata-ids"),
        pytest.param(_FNV32, _shadow_slots, id="shadow-slot-names"),
        pytest.param(_FNV64, _css_path, id="css-path-ids"),
        pytest.param(_FNV64, _radio_group, id="radio-group-form-ids"),
        pytest.param(_FNV32, _css_rule_selectors, id="css-rule-selectors"),
        pytest.param(_XSLT64, _xsd_prefixes, id="xsd-namespace-prefixes"),
        pytest.param(_XSLT64, _relaxng_defines, id="relaxng-defines"),
        pytest.param(_XSLT64, _xsd_attributes, id="xsd-attribute-names"),
        pytest.param(_FNV32, _xpath_namespace_uris, id="xpath-namespace-uris"),
    ],
)
def test_names_on_one_home_slot_stay_within_the_step_budget(
    work_steps: WorkSteps, fnv: tuple[int, int], build: Callable[[list[str]], Callable[[], object]]
) -> None:
    collide = ["".join(choice) for choice in itertools.product(*_block_pairs(fnv, _STEPS))]
    work_steps.assert_within(build(collide), build(_spread(len(collide), len(collide[0]))), factor=_FACTOR)


def _block_pairs(fnv: tuple[int, int], steps: int) -> list[tuple[str, str]]:
    # Two three-letter blocks that take the same low 16 bits of FNV-1a state to the same low 16 bits, chained: the low
    # bits of the state only ever depend on the low bits before them, so any choice of one block per pair lands there.
    basis, prime = fnv
    state = basis & _LOW
    pairs: list[tuple[str, str]] = []
    for _ in range(steps):
        groups: dict[int, list[str]] = {}
        for letters in itertools.product(string.ascii_lowercase, repeat=3):
            block = "".join(letters)
            low = state
            for char in block:
                low = ((low ^ ord(char)) * prime) & _LOW
            groups.setdefault(low, []).append(block)
        shared = next(key for key, blocks in groups.items() if len(blocks) >= 2)
        pairs.append((groups[shared][0], groups[shared][1]))
        state = shared
    return pairs


def test_attribute_lookup_after_the_name_table_moved_to_the_keyed_hash() -> None:
    names: Final = ["".join(choice) for choice in itertools.product(*_block_pairs(_FNV32, _STEPS))]
    document: Final = turbohtml.parse(_attribute_tag(names))

    found = (document.select(f"i[{names[-1]}]"), document.select("i[absent]"))

    assert (len(found[0]), len(found[1])) == (1, 0)


def test_attribute_name_interned_again_after_the_name_table_moved_to_the_keyed_hash() -> None:
    names: Final = ["".join(choice) for choice in itertools.product(*_block_pairs(_FNV32, _STEPS))]
    document: Final = turbohtml.parse(f"{_attribute_tag(names)}<i {names[0]}>")

    assert len(document.select(f"i[{names[0]}]")) == 2


def test_xsl_key_duplicate_value_after_the_map_moved_to_the_keyed_hash() -> None:
    names: Final = ["".join(choice) for choice in itertools.product(*_block_pairs(_XSLT64, _STEPS))]

    assert _xsl_key(names + names[:1])() == str(len(names) + 1)


def test_duplicate_slot_names_after_the_slot_index_moved_to_the_keyed_hash() -> None:
    names: Final = ["".join(choice) for choice in itertools.product(*_block_pairs(_FNV32, _STEPS))]
    slots: Final = "".join(f"<slot name={name}></slot>" for name in [*names, *names[:4]])
    children: Final = "".join(f"<b slot={name}>{name}</b>" for name in names[:4])
    document: Final = turbohtml.parse(f"<div><template shadowrootmode=open>{slots}</template>{children}</div>")

    assert [node.text for node in document.select("div")[0].flattened_children] == names[:4]


def _attribute_misses(
    build: Callable[[list[str]], Callable[[], object]],
) -> Callable[[list[str], list[str]], Callable[[], object]]:
    return lambda run, misses: build(run + misses)


def _xpath_id_misses(run: list[str], misses: list[str]) -> Callable[[], object]:
    # The tokens go from the last home back, so none is seated behind a filled slot and only a miss finds the run.
    document: Final = turbohtml.parse(
        f'<input aria-labelledby="{" ".join(reversed(run))}">{"".join(f"<p id={name}>" for name in misses)}'
    )
    return lambda: document.xpath("id(//input/@aria-labelledby)")


def _xsl_key_misses(run: list[str], misses: list[str]) -> Callable[[], object]:
    items: Final = "".join(f'<item id="{name}"/>' for name in run) + "".join(f'<probe v="{name}"/>' for name in misses)
    source: Final = turbohtml.parse_xml(f"<items>{items}</items>")
    transform: Final = Transform(
        turbohtml.parse_xml(
            '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">'
            '<xsl:output method="text"/><xsl:key name="by-id" match="item" use="@id"/>'
            '<xsl:template match="/"><xsl:value-of select="count(key(\'by-id\', //probe/@v))"/></xsl:template>'
            "</xsl:stylesheet>"
        ),
        allow_imports=False,
    )
    return lambda: transform(source)


def _xsl_attribute_set_misses(run: list[str], misses: list[str]) -> Callable[[], object]:
    # An attribute set that use-attribute-sets names but the stylesheet never declares is skipped, so every element
    # walks each such miss again.
    sets: Final = "".join(f'<xsl:attribute-set name="{name}"/>' for name in run)
    sheet: Final = turbohtml.parse_xml(
        f'<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">{sets}'
        f'<xsl:template match="/"><r xsl:use-attribute-sets="{" ".join(misses)}"/></xsl:template></xsl:stylesheet>'
    )
    source: Final = turbohtml.parse_xml("<r/>")
    return lambda: Transform(sheet, allow_imports=False)(source)


def _shadow_slot_misses(run: list[str], misses: list[str]) -> Callable[[], object]:
    # Light children name slots the shadow root never declares, so each one's fill walks the run of declared slots.
    # Every fourth declared slot also gets a child, so some lookups end their FNV-1a walk on an empty slot.
    slots: Final = "".join(f"<slot name={name}></slot>" for name in run)
    children: Final = "".join(f"<b slot={name}>y</b>" for name in [*misses, *run[::4]])
    document: Final = turbohtml.parse(f"<div><template shadowrootmode=open>{slots}</template>{children}</div>")
    return lambda: document.select("div")[0].flattened_children


def _minify_js_misses(run: list[str], misses: list[str]) -> Callable[[], object]:
    # Each absent name is read four times, so its misses outweigh the steps the mangler takes on any source this size.
    source: Final = f"function f(){{var {','.join(run)};return [{','.join(misses * 4)}]}}"
    return lambda: minify_js(source)


@pytest.mark.parametrize(
    ("fnv", "build"),
    [
        pytest.param(_FNV32, _attribute_misses(_tokenize), id="tokenizer-attribute-names"),
        pytest.param(_FNV32, _attribute_misses(_parse), id="tree-attribute-names"),
        pytest.param(_FNV64, _xpath_id_misses, id="xpath-id-tokens"),
        pytest.param(_XSLT64, _xsl_key_misses, id="xsl-key-values"),
        pytest.param(_XSLT64, _xsl_attribute_set_misses, id="xsl-attribute-set-names"),
        pytest.param(_FNV32, _minify_js_misses, id="minify-js-names"),
        pytest.param(_FNV32, _shadow_slot_misses, id="shadow-slot-names"),
    ],
)
def test_misses_along_lined_up_homes_stay_within_the_step_budget(
    work_steps: WorkSteps, fnv: tuple[int, int], build: Callable[[list[str], list[str]], Callable[[], object]]
) -> None:
    run, misses = _lined_up(fnv)
    control = _spread(len(run) + len(misses), len(run[0]))
    work_steps.assert_within(build(run, misses), build(control[: len(run)], control[len(run) :]), factor=_FACTOR)


def _lined_up(fnv: tuple[int, int], base: int = 0) -> tuple[list[str], list[str]]:
    # _LINED_UP names on consecutive home slots from base, each seated on its own home, and as many absent names, one
    # more on each of those homes: a miss walks to the end of the run although no name sits away from its home. The low
    # 16 bits make the homes consecutive in any table of _LINED_UP to 2**16 slots.
    basis, prime = fnv
    prefixes: dict[int, str] = {}
    for letters in itertools.product(string.ascii_lowercase, repeat=3):
        state = basis & _LOW
        for char in letters:
            state = ((state ^ ord(char)) * prime) & _LOW
        prefixes.setdefault(state, "".join(letters))
    run, misses = zip(*(_ending_at(fnv, prefixes, (base + home) & _LOW)[:2] for home in range(_LINED_UP)), strict=True)
    return list(run), list(misses)


def _ending_at(fnv: tuple[int, int], prefixes: dict[int, str], target: int) -> list[str]:
    # Undo the last two letters from target (the prime is odd, so it has an inverse modulo 2**16) and look the state
    # before them up among the prefixes: the five-letter names whose FNV-1a state ends with low 16 bits target.
    inverse = pow(fnv[1], -1, _LOW + 1)
    names: list[str] = []
    for first, second in itertools.product(string.ascii_lowercase, repeat=2):
        state = (((target * inverse) & _LOW) ^ ord(second)) * inverse & _LOW ^ ord(first)
        if (prefix := prefixes.get(state)) is not None:
            names.append(prefix + first + second)
    return names


def test_translate_characters_on_one_home_slot_stay_within_the_step_budget(work_steps: WorkSteps) -> None:
    # The multiplicative hash keeps the product's low bits, which code points that agree in their low bits share.
    work_steps.assert_within(
        _translate(_code_points(0x400, _TRANSLATE_CAPACITY)), _translate(_code_points(0x400, 1)), factor=_FACTOR
    )


def _translate(characters: list[str]) -> Callable[[], object]:
    source: Final = "".join(characters)
    document: Final = turbohtml.parse_xml(f"<r>{source * 8}</r>")
    return lambda: document.xpath(f"translate(string(/r), '{source}', '{source[::-1]}')")


def _code_points(start: int, stride: int) -> list[str]:
    # Code points from start in steps of stride, skipping the surrogates and the two noncharacters XML rejects.
    points = (point for point in range(start, 0x110000, stride) if not 0xD800 <= point <= 0xDFFF)
    return [chr(point) for point in itertools.islice(points, _TRANSLATE_FROM) if point & 0xFFFE != 0xFFFE]


def test_translate_misses_along_lined_up_homes_stay_within_the_step_budget(work_steps: WorkSteps) -> None:
    # Every from character on its own home, the homes in one run that wraps past the last slot, and a text of absent
    # characters on the same homes: each miss walks to the end of the run although no character sits away from home.
    homes: Final = range(_TRANSLATE_CAPACITY - 100, _TRANSLATE_CAPACITY - 100 + _TRANSLATE_FROM)
    work_steps.assert_within(
        _translate_misses(_on_homes(homes, _TRANSLATE_CAPACITY), _on_homes(homes, 2 * _TRANSLATE_CAPACITY)),
        _translate_misses(_code_points(0x400, 1), _code_points(0x800, 1)),
        factor=_FACTOR,
    )


def _translate_misses(source: list[str], misses: list[str]) -> Callable[[], object]:
    document: Final = turbohtml.parse_xml(f"<r>{''.join(misses) * 4}</r>")
    return lambda: document.xpath(f"translate(string(/r), '{''.join(source)}', '')")


def _on_homes(homes: range, offset: int) -> list[str]:
    # The code points from offset whose multiplicative hash puts them on each of homes in _TRANSLATE_CAPACITY slots.
    inverse: Final = pow(_TRANSLATE_MULTIPLIER, -1, _TRANSLATE_CAPACITY)
    return [chr(home % _TRANSLATE_CAPACITY * inverse % _TRANSLATE_CAPACITY + offset) for home in homes]


def test_translate_keeps_a_short_lined_up_run() -> None:
    source: Final = "".join(_on_homes(range(40), _TRANSLATE_CAPACITY)) + "".join(chr(0x3000 + 7 * i) for i in range(60))
    target: Final = "".join(chr(0x4000 + index) for index in range(len(source)))
    text: Final = f"{source}xyz" * 4
    document: Final = turbohtml.parse_xml(f"<r>{text}</r>")

    result = document.xpath(f"translate(string(/r), '{source}', '{target}')")

    assert result == text.translate(str.maketrans(source, target))


def test_translate_duplicate_from_character_on_the_keyed_fill() -> None:
    source: Final = "".join(_code_points(0x400, _TRANSLATE_CAPACITY))
    target: Final = source[::-1]
    text: Final = source * 8
    document: Final = turbohtml.parse_xml(f"<r>{text}</r>")

    result = document.xpath(f"translate(string(/r), '{source}{source[0]}', '{target}Z')")

    assert result == text.translate(str.maketrans(source, target))


def test_css_path_in_quirks_mode_after_the_id_map_moved_to_the_keyed_hash() -> None:
    names: Final = ["".join(choice) for choice in itertools.product(*_block_pairs(_FNV64, _STEPS))]
    long_id: Final = "q" * 70  # longer than the 64-code-point buffer the case-folding hash works in
    document: Final = turbohtml.parse("".join(f"<p id={name}>" for name in [*names, long_id]))

    assert document.select("p")[-1].css_path() == f"#{long_id}"


def test_radio_form_miss_after_the_id_table_moved_to_the_keyed_hash() -> None:
    run, misses = _lined_up(_FNV64)
    forms: Final = "".join(f"<form id={name}></form>" for name in run)
    # The first miss moves the table to the keyed hash; the later ones look up a form id whose FNV-1a home is empty.
    misses_radios: Final = "".join(f"<input type=radio name=g checked form={name}>" for name in misses[:21])
    document: Final = turbohtml.parse(
        f"{forms}<input type=radio name=g checked form={run[0]}>{misses_radios}<input type=radio name=g>"
    )
    radios: Final = document.select("input")

    radios[-1].checked = True

    assert [radio.checked for radio in radios] == [True, *[False] * 21, True]


def test_wide_keyword_resets_a_longhand_after_the_declaration_table_moved_to_the_keyed_hash() -> None:
    # The shorthand's own name starts the walk over the run, so the FNV-1a pass gives up and the keyed pass drops the
    # longhand the keyword resets.
    run, _ = _lined_up(_FNV32, _low_state(_FNV32, "margin"))
    declarations: Final = ";".join(f"{name}:1" for name in run)

    assert minify_css(f"p{{margin-top:9px;{declarations};margin:inherit}}") == minify_css(
        f"p{{{declarations};margin:inherit}}"
    )


def _low_state(fnv: tuple[int, int], text: str) -> int:
    basis, prime = fnv
    state = basis & _LOW
    for char in text:
        state = ((state ^ ord(char)) * prime) & _LOW
    return state


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        pytest.param(_xsl_key_names, "1", id="xsl-key-names"),
        pytest.param(_xsl_named_templates, "ok", id="xsl-template-names"),
    ],
)
def test_xsl_names_lined_up_across_the_end_of_the_index_still_resolve(
    build: Callable[[list[str]], Callable[[], object]], expected: str
) -> None:
    # The run starts 100 slots before the end of a 1024-slot index, so the walk from its first full block runs back
    # across the end, and the lookup of its last name must still find the declaration.
    names, _ = _lined_up(_XSLT64, 1024 - 100)

    assert build(names)() == expected
