"""Reading and writing Element.checked, including radio-group exclusivity."""

from __future__ import annotations

from typing import Any

import pytest

from turbohtml import Element, parse


def _control(markup: str, selector: str) -> Element:
    element = parse(markup).find(selector)
    assert element is not None
    return element


def test_checked_reads_the_attribute() -> None:
    assert _control("<input type=checkbox checked>", "input").checked is True


def test_unchecked_reads_false() -> None:
    assert _control("<input type=checkbox>", "input").checked is False


def test_non_control_reads_false() -> None:
    assert _control("<div></div>", "div").checked is False


def test_set_checked_true_adds_the_attribute() -> None:
    field = _control("<input type=checkbox>", "input")
    field.checked = True
    assert field.checked is True
    assert field.html == '<input type="checkbox" checked="">'


def test_set_checked_false_removes_the_attribute() -> None:
    field = _control("<input type=checkbox checked>", "input")
    field.checked = False
    assert field.checked is False
    assert field.html == '<input type="checkbox">'


def test_set_checked_accepts_truthy_values() -> None:
    field: Any = _control("<input type=radio>", "input")
    field.checked = 1
    assert field.checked is True


def test_set_checked_propagates_a_failing_bool() -> None:
    class Boom:
        def __bool__(self) -> bool:
            raise ValueError("nope")

    field: Any = _control("<input type=checkbox>", "input")
    with pytest.raises(ValueError, match="nope"):
        field.checked = Boom()


def test_set_checked_on_a_text_input_raises() -> None:
    field = _control("<input type=text>", "input")
    with pytest.raises(TypeError, match="checkbox or radio"):
        field.checked = True


def test_set_checked_on_a_typeless_input_raises() -> None:
    field = _control("<input>", "input")
    with pytest.raises(TypeError, match="checkbox or radio"):
        field.checked = True


def test_set_checked_on_a_valueless_type_input_raises() -> None:
    field = _control("<input type>", "input")
    with pytest.raises(TypeError, match="checkbox or radio"):
        field.checked = True


def test_set_checked_on_a_non_input_raises() -> None:
    element = _control("<div></div>", "div")
    with pytest.raises(TypeError, match="checkbox or radio"):
        element.checked = True


def test_delete_checked_raises() -> None:
    field: Any = _control("<input type=checkbox checked>", "input")
    with pytest.raises(TypeError, match="cannot delete checked"):
        del field.checked


def test_checking_a_radio_clears_the_group() -> None:
    form = _control(
        "<form><input type=radio name=size value=s checked>"
        "<input type=radio name=size value=m>"
        "<input type=radio name=size value=l></form>",
        "form",
    )
    radios = form.find_all("input")
    radios[1].checked = True
    assert [radio.checked for radio in radios] == [False, True, False]


def test_checking_a_radio_leaves_other_names_alone() -> None:
    form = _control(
        "<form><input type=radio name=a value=1 checked>"
        "<input type=radio name=b value=2 checked>"
        "<input type=radio name=size value=3 checked></form>",
        "form",
    )
    radios = form.find_all("input")
    radios[0].checked = True  # name "a" matches neither the same-length "b" nor the longer "size"
    assert [radio.checked for radio in radios] == [True, True, True]


def test_checking_a_nameless_radio_clears_nothing() -> None:
    form = _control(
        "<form><input type=radio value=1 checked><input type=radio value=2></form>",
        "form",
    )
    radios = form.find_all("input")
    radios[1].checked = True
    assert [radio.checked for radio in radios] == [True, True]


def test_checking_a_valueless_named_radio_clears_nothing() -> None:
    form = _control(
        "<form><input type=radio name value=1 checked><input type=radio name value=2></form>",
        "form",
    )
    radios = form.find_all("input")
    radios[1].checked = True
    assert [radio.checked for radio in radios] == [True, True]


def test_checking_a_blank_named_radio_clears_nothing() -> None:
    form = parse("<form></form>").find("form")
    assert form is not None
    first = Element("input", {"type": "radio", "name": "", "value": "1", "checked": None})
    second = Element("input", {"type": "radio", "name": "", "value": "2"})
    form.extend([first, second])  # an empty string name is a real but blank name, distinct from a valueless one
    second.checked = True
    assert [first.checked, second.checked] == [True, True]


def test_radio_group_skips_unrelated_controls_in_scope() -> None:
    form = _control(
        "<form>"
        "<input type=radio name=s value=a checked>"  # target
        "<input type=radio name=s value=b checked>"  # same name -> cleared
        "<input type=radio name=x value=c checked>"  # same-length name -> kept
        "<input type=radio name=size value=d checked>"  # different-length name -> kept
        "<input type=radio value=e checked>"  # no name -> kept
        "<input type=radio name value=f checked>"  # valueless name -> kept
        "<input type=checkbox name=s value=g checked>"  # not a radio -> kept
        "<input type=text name=s value=h>"  # not a radio -> untouched
        "<label>pick</label>"  # not an input -> untouched
        "</form>",
        "form",
    )
    radios = form.find_all("input")
    radios[0].checked = True
    assert [field.checked for field in radios] == [True, False, True, True, True, True, True, False]


def test_radio_group_falls_back_to_the_document() -> None:
    document = parse("<input type=radio name=g value=1 checked><input type=radio name=g value=2>")
    radios = document.find_all("input")
    radios[1].checked = True
    assert [radio.checked for radio in radios] == [False, True]


def test_radio_group_is_scoped_to_the_owning_form() -> None:
    document = parse(
        "<input type=radio name=g value=outside checked>"
        "<form><input type=radio name=g value=inside></form>"
    )
    form = document.find("form")
    assert form is not None
    inside = form.find("input")
    assert inside is not None
    inside.checked = True
    outside = document.find_all("input")[0]
    assert outside.checked is True
    assert inside.checked is True


def test_unchecking_a_radio_leaves_the_group() -> None:
    form = _control(
        "<form><input type=radio name=s value=1 checked><input type=radio name=s value=2 checked></form>",
        "form",
    )
    radios = form.find_all("input")
    radios[0].checked = False
    assert [radio.checked for radio in radios] == [False, True]
