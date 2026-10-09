from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Final

import pytest

import turbohtml
from turbohtml.clean import Policy, Sanitizer

if TYPE_CHECKING:
    from collections.abc import Callable

_SANITIZER: Final = Sanitizer(Policy.strict())
# Elements only: a text node would add a lazy text copy, which these tests do not target. The custom attribute names
# make every copy intern them again in its own tree.
_TREE: Final = "<b zq=1><i></i></b><x y=1></x>"
# the input, the radio and the option carry enough attributes that adding value, checked or selected outgrows their
# arena block
_INPUT: Final = "<input a0=1 a1=1 a2=1>"
_RADIO: Final = "<form id=f></form><input type=radio name=r form=f a=1 b=2 c=3 d=4 e=5 f=6 g=7>"
_SELECT: Final = "<select><option value=a a0=1 a1=1></option></select>"


@pytest.mark.parametrize(
    ("markup", "call"),
    [
        pytest.param(_TREE, _SANITIZER.sanitize_node, id="sanitize-node"),
        # enough escaped tags that the sanitizer's text nodes outgrow the copy's first arena blocks
        pytest.param("<x y=1></x>" * 4, _SANITIZER.sanitize_node, id="sanitize-escaped-tags"),
        pytest.param(_TREE, copy.copy, id="copy"),
        pytest.param(_TREE, lambda _: turbohtml.Element("p", {"zq": "1", "yq": ""}), id="element"),
        pytest.param(_TREE, lambda fragment: fragment.children[0].attrs.__setitem__("zr", "1"), id="set-attribute"),
        pytest.param(_INPUT, lambda fragment: setattr(fragment.children[0], "field_value", "v"), id="input-value"),
        pytest.param(_RADIO, lambda fragment: setattr(fragment.children[1], "checked", True), id="radio-checked"),
        pytest.param(_SELECT, lambda fragment: setattr(fragment.children[0], "field_value", "a"), id="select-value"),
    ],
)
def test_dom_construction_allocation_failure_raises_memory_error(
    alloc_sweep: Callable[..., list[str]], markup: str, call: Callable[[turbohtml.Node], object]
) -> None:
    assert set(alloc_sweep(call, lambda: turbohtml.parse_fragment(markup))) == {"MemoryError"}
