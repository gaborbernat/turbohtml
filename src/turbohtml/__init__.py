"""turbohtml: fast, typed HTML utilities powered by a C-accelerated core."""

from __future__ import annotations

from importlib.metadata import version

from ._html import escape, unescape

__version__ = version("turbohtml")
"""The installed package version."""

__all__ = [
    "__version__",
    "escape",
    "unescape",
]
