"""The live mutable attribute view and the data/text setters."""

from __future__ import annotations

import pytest

from turbohtml import Comment, Element, Text, parse


def _div(markup: str = '<div id="a" class="x y">') -> Element:
    element = parse(markup).find("div")
    assert element is not None
    return element


def test_attrs_is_a_live_view() -> None:
    element = _div()
    element.attrs["data-z"] = "1"  # mutating the view rewrites the element
    assert element.html == '<div id="a" class="x y" data-z="1"></div>'


def test_attrs_set_replaces_an_existing_value() -> None:
    element = _div()
    element.attrs["class"] = ["p", "q"]  # a list joins like construction does
    assert element.html == '<div id="a" class="p q"></div>'
    assert element.attrs["class"] == ["p", "q"]


def test_attrs_set_valueless_and_empty() -> None:
    element = parse("<input>").find("input")
    assert element is not None
    element.attrs["disabled"] = None  # None sets an empty (valueless) attribute
    element.attrs["value"] = ""
    assert element.html == '<input disabled="" value="">'
    # a valueless or empty attribute reads back as the empty string, like getAttribute
    assert element.attrs["disabled"] == ""  # noqa: PLC1901  # exactly "", not None
    assert element.attrs["value"] == ""  # noqa: PLC1901  # exactly ""


def test_attrs_set_existing_to_empty() -> None:
    element = _div('<div id="a">')
    element.attrs["id"] = None  # None clears an existing value to empty
    assert element.attrs["id"] == ""  # noqa: PLC1901  # exactly "", not None
    assert element.html == '<div id=""></div>'


def test_attrs_set_lowercases_the_name() -> None:
    element = _div("<div>")
    element.attrs["DATA-X"] = "1"
    assert element.attrs["data-x"] == "1"  # stored lowercased, like the parser


def test_attrs_delete() -> None:
    element = _div()
    del element.attrs["id"]
    assert element.html == '<div class="x y"></div>'


@pytest.mark.parametrize(
    "name",
    # a dynamic name and a known atom hit different lookup tables, both must miss
    [pytest.param("never-seen-name", id="dynamic"), pytest.param("title", id="known-atom")],
)
def test_attrs_delete_missing_name_raises(name: str) -> None:
    with pytest.raises(KeyError):
        del _div().attrs[name]


def test_attrs_set_rejects_non_str_name() -> None:
    with pytest.raises(TypeError, match="attribute name must be a str"):
        _div().attrs[5] = "x"  # ty: ignore[invalid-assignment]  # names must be str


def test_attrs_delete_rejects_non_str_name() -> None:
    with pytest.raises(TypeError, match="attribute name must be a str"):
        del _div().attrs[5]  # ty: ignore[invalid-argument-type]  # names must be str


@pytest.mark.parametrize(
    "name",
    [pytest.param("", id="empty"), pytest.param("a b", id="space"), pytest.param("a=b", id="eq")],
)
def test_attrs_set_rejects_invalid_name(name: str) -> None:
    with pytest.raises(ValueError, match=r"empty|invalid character"):
        _div().attrs[name] = "x"


def test_attrs_set_rejects_bad_value() -> None:
    with pytest.raises(TypeError, match="attribute value"):
        _div().attrs["x"] = 1  # ty: ignore[invalid-assignment]  # value must be str/list/None


@pytest.mark.parametrize(
    "name",
    # "title" is a known atom that happens to be absent; "" can never be a stored name
    [pytest.param("title", id="known-atom-absent"), pytest.param("", id="empty")],
)
def test_attrs_getitem_missing_raises_keyerror(name: str) -> None:
    with pytest.raises(KeyError):
        _ = _div().attrs[name]


def test_attrs_getitem_rejects_non_str_name() -> None:
    with pytest.raises(TypeError, match="attribute name must be a str"):
        _ = _div().attrs[5]  # ty: ignore[invalid-argument-type]  # names must be str


def test_attrs_len_and_iter_keep_source_order() -> None:
    element = _div('<div id="a" class="x" data-z="1">')
    assert len(element.attrs) == 3
    assert list(element.attrs) == ["id", "class", "data-z"]


def test_attrs_get_returns_value_or_default() -> None:
    attrs = _div().attrs
    assert attrs.get("id") == "a"
    assert attrs.get("missing") is None
    assert attrs.get("missing", "d") == "d"
    assert attrs.get(5, "d") == "d"  # a non-str key falls back to the default


def test_attrs_get_needs_a_key() -> None:
    with pytest.raises(TypeError):
        _div().attrs.get()  # ty: ignore[no-matching-overload]  # get requires a key


def test_attrs_contains() -> None:
    attrs = _div().attrs
    assert "id" in attrs
    assert "missing" not in attrs
    assert 5 not in attrs  # a non-str key is never present


def test_attrs_keys_values_items() -> None:
    attrs = _div('<div id="a" class="x y">').attrs
    assert attrs.keys() == ["id", "class"]
    assert attrs.values() == ["a", ["x", "y"]]
    assert attrs.items() == [("id", "a"), ("class", ["x", "y"])]


def test_attrs_repr_reads_like_a_dict() -> None:
    assert repr(_div('<div id="a">').attrs) == "{'id': 'a'}"


def test_attrs_round_trips_through_dict() -> None:
    assert dict(_div('<div id="a" class="x">').attrs) == {"id": "a", "class": ["x"]}


# --- data setter ---


def test_data_setter_replaces_text() -> None:
    text = Text("old")
    text.data = "new & shiny"
    assert text.data == "new & shiny"
    assert text.html == "new &amp; shiny"


def test_data_setter_on_comment() -> None:
    comment = Comment("a")
    comment.data = ""
    assert comment.html == "<!---->"


def test_data_setter_on_a_parsed_text_node() -> None:
    text = next(child for child in _div("<div>hi</div>").children if isinstance(child, Text))
    text.data = "bye"
    assert text.data == "bye"


def test_data_setter_rejects_non_str() -> None:
    with pytest.raises(TypeError, match="data must be a str"):
        Text("x").data = 5  # ty: ignore[invalid-assignment]  # data must be a str


def test_data_cannot_be_deleted() -> None:
    text = Text("x")
    with pytest.raises(TypeError, match="cannot delete data"):
        del text.data  # ty: ignore[invalid-assignment]  # data has no deleter


# --- text setter ---


def test_text_setter_replaces_children() -> None:
    element = parse("<p><b>x</b>y</p>").find("p")
    assert element is not None
    element.text = "Tom & Jerry"
    assert element.html == "<p>Tom &amp; Jerry</p>"
    assert len(element) == 1


def test_text_setter_empty_clears() -> None:
    element = parse("<p><b>x</b>y</p>").find("p")
    assert element is not None
    element.text = ""
    assert element.html == "<p></p>"
    assert len(element) == 0


def test_text_setter_rejects_non_str() -> None:
    element = _div()
    with pytest.raises(TypeError, match="text must be a str"):
        element.text = 5  # ty: ignore[invalid-assignment]  # text must be a str


def test_text_cannot_be_deleted() -> None:
    element = _div()
    with pytest.raises(TypeError, match="cannot delete text"):
        del element.text  # ty: ignore[invalid-assignment]  # text has no deleter
