"""
Smart-string xpath results, mirroring lxml's ``_ElementUnicodeResult``.

When :meth:`turbohtml.Node.xpath` is called with ``smart_strings=True``, an
attribute or ``text()`` value comes back as an :class:`XPathString`: a ``str``
that also remembers the element it was selected from, so ``result.getparent()``
walks back into the tree and ``result.is_attribute`` / ``result.attrname``
identify where it came from. The C core constructs these; importing this module
registers the type with it.
"""

from __future__ import annotations

from collections import UserString

from typing_extensions import Self

from ._html import Element, _register_xpath_string  # Element stays importable so autodoc resolves it


class XPathString(UserString):
    """A string xpath result that remembers the element it came from."""

    _parent: Element
    is_attribute: bool
    is_text: bool
    is_tail: bool
    attrname: str | None

    def __new__(cls, value: str, parent: Element, is_attribute: bool, attrname: str | None) -> Self:  # noqa: FBT001
        self = super().__new__(cls, value)
        self._parent = parent
        self.is_attribute = is_attribute
        self.is_text = not is_attribute
        self.is_tail = False
        self.attrname = attrname
        return self

    def getparent(self) -> Element:
        """Return the element this attribute or text value was selected from."""
        return self._parent


_register_xpath_string(XPathString)
