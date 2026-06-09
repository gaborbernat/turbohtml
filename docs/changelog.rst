###########
 Changelog
###########

.. towncrier-draft-entries:: Unreleased

.. towncrier release notes start

*********************
 v0.1.0 (2026-06-09)
*********************

Features - 0.1.0
================

- Add C-accelerated :func:`turbohtml.escape` and :func:`turbohtml.unescape`, matching :func:`python:html.escape` and
  :func:`python:html.unescape` byte for byte, with free-threading support and per-interpreter wheels for CPython 3.10
  through 3.15 - by :user:`gaborbernat`. (:issue:`1`)
- Speed up ``escape`` of non-ASCII (UCS-2/UCS-4) text that needs no escaping by probing for special characters with a
  vectorized scan instead of a scalar one, making it several times faster and ahead of :func:`python:html.escape` - by
  :user:`gaborbernat`. (:issue:`3`)

Improved documentation - 0.1.0
==============================

- Document the measured ``escape``/``unescape`` speedups over the standard library in the README and the docs, add a
  reproducible benchmark behind ``tox -e bench``, and give the API reference typed signatures with intersphinx links -
  by :user:`gaborbernat`. (:issue:`2`)

Miscellaneous internal changes - 0.1.0
======================================

- Automate releases the tox-dev way: git-tag-derived versioning, a towncrier-managed changelog, and a manual
  prepare-release workflow that tags and triggers the trusted-publishing wheel build - by :user:`gaborbernat`.
  (:issue:`1`)
