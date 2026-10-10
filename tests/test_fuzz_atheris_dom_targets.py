from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Final

import pytest
from fuzz.atheris_dom_targets import DomObservation, dom_observation, dom_targets

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_DOMAINS: Final = (
    "dom-construction",
    "dom-elementtree",
    "dom-traversal",
    "dom-query",
    "dom-mutation",
    "dom-range",
    "dom-shadow",
    "dom-locations",
    "dom-rewrite",
    "dom-sax",
    "dom-treebuild",
)


@pytest.mark.parametrize("domain", _DOMAINS)
@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"text", id="plain"),
        pytest.param("é水😀".encode(), id="unicode"),
        pytest.param(b"<&>\r\n\x00", id="escaped"),
    ],
)
def test_dom_independent_contract(domain: str, data: bytes) -> None:
    observation: Final = dom_observation(data, domain)
    assert observation.actual == observation.expected


@pytest.mark.parametrize("domain", _DOMAINS)
def test_dom_registered_callback(domain: str) -> None:
    target: Final = next(target for target in dom_targets() if target.name == domain)
    assert target.exceptions == (UnicodeDecodeError,)
    target.callback(b"text")
    with pytest.raises(UnicodeDecodeError):
        target.callback(b"\xff")


def test_dom_ownership() -> None:
    targets: Final = dom_targets()
    exports: Final = [export for target in targets for export in target.exports]
    assert (tuple(target.name for target in targets), len(exports), len(set(exports))) == (_DOMAINS, 78, 78)


def test_dom_verification_rejects_changed_result() -> None:
    with pytest.raises(AssertionError, match=r"actual.*expected"):
        DomObservation("actual", "expected").verify()


def test_dom_verification_accepts_observed_result() -> None:
    assert dom_observation(b"text", "dom-range").verify() is None


def test_dom_range_literal() -> None:
    assert dom_observation(b"<&>", "dom-range").actual == repr(("<p>&lt;&amp;&gt;</p>", 0, 1, 0, 1, False, "<&>"))


def test_dom_input_bound() -> None:
    assert dom_observation(b"x" * 65, "dom-range") == dom_observation(b"x" * 64, "dom-range")


def test_dom_unknown_domain() -> None:
    with pytest.raises(KeyError, match="unknown"):
        dom_observation(b"text", "unknown")


def test_dom_elementtree_without_lxml(mocker: MockerFixture) -> None:
    mocker.patch.dict(sys.modules, {"lxml.etree": None})
    assert dom_observation(b"text", "dom-elementtree").actual == repr((
        True,
        True,
        True,
        "prefixtexttail",
        "prefixtext",
        "prefixtext",
        "trailing",
        None,
        None,
        None,
    ))
