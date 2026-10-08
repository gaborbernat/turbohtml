"""The ``_fuzz_`` hooks exist in the fuzz build alone, which ``tox r -e fuzz-smoke`` runs this module against."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from turbohtml import NodeIterator, _html, parse
from turbohtml._html import _tree_verify

if TYPE_CHECKING:
    from collections.abc import Callable

    from turbohtml import Node

# the stubs describe the production module, which lacks the hook
_ESCAPE_ITERATORS: Final[Callable[[Node], int]] = vars(_html)["_fuzz_escape_iterators"]


def test_tree_verify_counts_an_iterator_reference_outside_its_root() -> None:
    document: Final = parse("<p><b></b></p>")
    iterator: Final = NodeIterator(document.select("p")[0])
    assert (_ESCAPE_ITERATORS(document), _tree_verify(document), iterator.reference_node) == (1, (0, 0, 1, 0), document)
