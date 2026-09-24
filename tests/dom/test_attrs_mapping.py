"""Element.attrs as a full MutableMapping: the dict-style mutators, equality, and the | operators."""

from __future__ import annotations

from collections.abc import MutableMapping
from types import MappingProxyType
from typing import TYPE_CHECKING, NoReturn

import pytest

from turbohtml import Element

if TYPE_CHECKING:
    from collections.abc import Callable


def _anchor() -> Element:
    return Element("a", {"id": "x", "class": "c1 c2", "href": "h"})


class _BrokenMapping:
    """A mapping-like object whose keys() raises, so copying it into a dict fails."""

    @staticmethod
    def keys() -> NoReturn:
        msg = "broken"
        raise RuntimeError(msg)


def test_attrs_is_a_mutable_mapping() -> None:
    assert isinstance(_anchor().attrs, MutableMapping)


def test_attrs_copy_is_a_dict_snapshot() -> None:
    element = _anchor()
    snapshot = element.attrs.copy()
    element.attrs["id"] = "changed"
    assert snapshot == {"id": "x", "class": ["c1", "c2"], "href": "h"}


def test_attrs_pop_returns_the_value() -> None:
    assert _anchor().attrs.pop("href") == "h"


def test_attrs_pop_removes_the_attribute() -> None:
    element = _anchor()
    element.attrs.pop("href")
    assert element.html == '<a id="x" class="c1 c2"></a>'


@pytest.mark.parametrize("key", [pytest.param("missing", id="absent-name"), pytest.param(3, id="non-str")])
def test_attrs_pop_missing_returns_the_default(key: object) -> None:
    assert _anchor().attrs.pop(key, "fallback") == "fallback"  # ty: ignore[no-matching-overload]


@pytest.mark.parametrize("key", [pytest.param("missing", id="absent-name"), pytest.param(3, id="non-str")])
def test_attrs_pop_missing_without_default_raises(key: object) -> None:
    with pytest.raises(KeyError):
        _anchor().attrs.pop(key)  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda attrs: attrs.pop(), id="pop"),
        pytest.param(lambda attrs: attrs.setdefault(), id="setdefault"),
    ],
)
def test_attrs_methods_require_a_key(call: Callable[[MutableMapping[str, str | list[str] | None]], object]) -> None:
    with pytest.raises(TypeError):
        call(_anchor().attrs)


def test_attrs_popitem_removes_the_last_pair() -> None:
    element = _anchor()
    assert (element.attrs.popitem(), element.html) == (("href", "h"), '<a id="x" class="c1 c2"></a>')


def test_attrs_popitem_on_empty_raises() -> None:
    with pytest.raises(KeyError, match="empty"):
        Element("a").attrs.popitem()


def test_attrs_clear_removes_everything() -> None:
    element = _anchor()
    element.attrs.clear()
    assert element.html == "<a></a>"


def test_attrs_setdefault_keeps_an_existing_value() -> None:
    element = _anchor()
    assert (element.attrs.setdefault("id", "other"), element.attrs["id"]) == ("x", "x")


def test_attrs_setdefault_stores_a_missing_value() -> None:
    element = _anchor()
    assert (element.attrs.setdefault("title", "t"), element.attrs["title"]) == ("t", "t")


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        pytest.param(3, "v", TypeError, id="non-str-name"),
        pytest.param("title", 3, TypeError, id="bad-value"),
    ],
)
def test_attrs_setdefault_rejects_invalid_input(key: object, value: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        _anchor().attrs.setdefault(key, value)  # ty: ignore[no-matching-overload]


@pytest.mark.parametrize(
    "apply",
    [
        pytest.param(lambda attrs: attrs.update({"title": "t"}), id="mapping"),
        pytest.param(lambda attrs: attrs.update([("title", "t")]), id="pairs"),
        pytest.param(lambda attrs: attrs.update(title="t"), id="keywords"),
        pytest.param(lambda attrs: attrs.update({"title": "x"}, title="t"), id="keywords-win"),
    ],
)
def test_attrs_update_sets_the_pairs(apply: Callable[[MutableMapping[str, str | list[str] | None]], None]) -> None:
    element = Element("a")
    apply(element.attrs)
    assert element.html == '<a title="t"></a>'


def test_attrs_update_without_arguments_changes_nothing() -> None:
    element = _anchor()
    element.attrs.update()
    assert element.html == '<a id="x" class="c1 c2" href="h"></a>'


def test_attrs_update_with_malformed_pairs_changes_nothing() -> None:
    element = _anchor()
    with pytest.raises(ValueError, match=r"length|pairs"):  # CPython and PyPy word the error differently
        element.attrs.update([("title", "t"), ("bad",)])  # ty: ignore[no-matching-overload]
    assert element.html == '<a id="x" class="c1 c2" href="h"></a>'


def test_attrs_update_takes_at_most_one_positional_argument() -> None:
    with pytest.raises(TypeError, match="update"):
        _anchor().attrs.update({}, {})  # ty: ignore[no-matching-overload]


def test_attrs_update_with_a_bad_value_raises() -> None:
    with pytest.raises(TypeError, match="attribute value"):
        _anchor().attrs.update({"title": 3})  # ty: ignore[no-matching-overload]


@pytest.mark.parametrize(
    ("other", "expected"),
    [
        pytest.param({"id": "x", "class": ["c1", "c2"], "href": "h"}, True, id="equal-dict"),
        pytest.param({"id": "x"}, False, id="different-dict"),
        pytest.param(MappingProxyType({"id": "x", "class": ["c1", "c2"], "href": "h"}), True, id="other-mapping"),
        pytest.param(_anchor().attrs, True, id="other-view"),
        pytest.param([("id", "x")], False, id="non-mapping"),
    ],
)
def test_attrs_equality(other: object, *, expected: bool) -> None:
    assert (_anchor().attrs == other) is expected


def test_attrs_inequality_with_a_dict() -> None:
    assert _anchor().attrs != {}


def test_attrs_ordering_is_unsupported() -> None:
    with pytest.raises(TypeError):
        _ = _anchor().attrs < {}  # ty: ignore[unsupported-operator]


def test_attrs_equality_with_a_broken_mapping_raises() -> None:
    with pytest.raises(RuntimeError, match="broken"):
        _ = _anchor().attrs == _BrokenMapping()


def test_attrs_is_unhashable() -> None:
    with pytest.raises(TypeError, match="unhashable"):
        hash(_anchor().attrs)


def test_attrs_or_mapping_returns_a_merged_dict() -> None:
    assert _anchor().attrs | {"href": "new"} == {"id": "x", "class": ["c1", "c2"], "href": "new"}


def test_mapping_or_attrs_returns_a_merged_dict() -> None:
    assert {"href": "old", "rel": "r"} | _anchor().attrs == {"href": "h", "rel": "r", "id": "x", "class": ["c1", "c2"]}


def test_attrs_or_attrs_returns_a_merged_dict() -> None:
    assert _anchor().attrs | Element("b", {"title": "t"}).attrs == {
        "id": "x",
        "class": ["c1", "c2"],
        "href": "h",
        "title": "t",
    }


def test_attrs_or_leaves_the_element_unchanged() -> None:
    element = _anchor()
    _ = element.attrs | {"title": "t"}
    assert element.html == '<a id="x" class="c1 c2" href="h"></a>'


@pytest.mark.parametrize(
    "combine",
    [
        pytest.param(lambda attrs: attrs | 3, id="non-mapping-right"),
        pytest.param(lambda attrs: 3 | attrs, id="non-mapping-left"),
    ],
)
def test_attrs_or_non_mapping_is_unsupported(combine: Callable[[object], object]) -> None:
    with pytest.raises(TypeError):
        combine(_anchor().attrs)


@pytest.mark.parametrize(
    "combine",
    [
        pytest.param(lambda attrs: attrs | _BrokenMapping(), id="broken-right"),
        pytest.param(lambda attrs: _BrokenMapping() | attrs, id="broken-left"),
    ],
)
def test_attrs_or_broken_mapping_raises(combine: Callable[[object], object]) -> None:
    with pytest.raises(RuntimeError, match="broken"):
        combine(_anchor().attrs)


def test_attrs_inplace_or_updates_the_element() -> None:
    element = _anchor()
    attrs = element.attrs
    attrs |= {"href": "new"}
    assert element.html == '<a id="x" class="c1 c2" href="new"></a>'


def test_attrs_inplace_or_non_mapping_is_unsupported() -> None:
    attrs = _anchor().attrs
    with pytest.raises(TypeError):
        attrs |= 3  # ty: ignore[unsupported-operator]


def test_attrs_inplace_or_with_a_bad_value_raises() -> None:
    attrs = _anchor().attrs
    with pytest.raises(TypeError, match="attribute value"):
        attrs |= {"title": 3}  # ty: ignore[unsupported-operator]
