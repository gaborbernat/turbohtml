"""Sphinx configuration for the turbohtml documentation."""

from __future__ import annotations

from importlib.metadata import version as _version

project = "turbohtml"
author = "Bernát Gábor"
project_copyright = "2026, Bernát Gábor and contributors"
release = _version("turbohtml")
version = ".".join(release.split(".")[:2])

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
]

html_theme = "furo"
html_title = "turbohtml"

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}
autodoc_member_order = "bysource"
nitpicky = True
