from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from turbohtml import Canonical, Html, PlainText, parse


@dataclass(frozen=True)
class _SortedHtml(Html):
    sort_attributes: bool = True


@dataclass(frozen=True)
class _ImageText(PlainText):
    images: bool = True


@dataclass(frozen=True)
class _CommentedCanonical(Canonical):
    with_comments: bool = True


@dataclass(frozen=True)
class _ExtendedHtml(_SortedHtml):
    extra: str = "value"


@dataclass(frozen=True)
class _ExtendedText(_ImageText):
    extra: str = "value"


@dataclass(frozen=True)
class _ExtendedCanonical(_CommentedCanonical):
    extra: str = "value"


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        pytest.param(Html(), '<p z="1" a="2"><img alt="picture"><!--note--></p>', id="html-default"),
        pytest.param(_SortedHtml(), '<p a="2" z="1"><img alt="picture"><!--note--></p>', id="html-subclass"),
        pytest.param(PlainText(), "", id="text-default"),
        pytest.param(_ImageText(), "picture", id="text-subclass"),
        pytest.param(Canonical(), b'<p a="2" z="1"><img alt="picture"></img></p>', id="canonical-default"),
        pytest.param(
            _CommentedCanonical(),
            b'<p a="2" z="1"><img alt="picture"></img><!--note--></p>',
            id="canonical-subclass",
        ),
    ],
)
def test_render_options_preserve_subclass_defaults(
    options: Html | PlainText | Canonical, expected: str | bytes
) -> None:
    assert _render(options) == expected


@pytest.mark.parametrize(
    "options",
    [
        pytest.param(_ExtendedHtml(), id="html"),
        pytest.param(_ExtendedText(), id="text"),
        pytest.param(_ExtendedCanonical(), id="canonical"),
    ],
)
def test_render_options_reject_subclass_extra_fields(options: Html | PlainText | Canonical) -> None:
    with pytest.raises(AttributeError, match="has no attribute 'extra'"):
        _render(options)


def _render(options: Html | PlainText | Canonical) -> str | bytes:
    document: Final = parse('<p z="1" a="2"><img alt="picture"><!--note--></p>').select("p")[0]
    if isinstance(options, Html):
        return document.serialize(options)
    if isinstance(options, PlainText):
        return document.to_text(options)
    return document.canonicalize(options)
