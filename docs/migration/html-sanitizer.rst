#####################
 From html-sanitizer
#####################

.. package-meta:: html-sanitizer matthiask/html-sanitizer

`html-sanitizer <https://github.com/matthiask/html-sanitizer>`_ is an allowlist sanitizer over lxml, configured with a
``settings`` dict carrying ``tags`` (a set), ``attributes`` (a per-tag dict), ``add_nofollow``, a ``sanitize_href``
scheme check, and whitespace/tag-merging normalization.

***************
 Why turbohtml
***************

``turbohtml.clean`` shares the allowlist stance, so the move is a settings-to-:class:`~turbohtml.clean.Policy`
translation rather than a rethink, but it adds full static typing, a frozen thread-safe policy, and the WHATWG tree
builder in C instead of an lxml parse, leading html-sanitizer by one to two orders of magnitude:

.. bench-table::
    :file: bench/html-sanitizer.json

*************
 The renames
*************

.. code-block:: python

    # html-sanitizer
    from html_sanitizer import Sanitizer

    Sanitizer({"tags": {"a", "p"}, "attributes": {"a": {"href"}}, "add_nofollow": True}).sanitize(text)

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - `html-sanitizer <https://github.com/matthiask/html-sanitizer>`__
      - turbohtml
    - - ``Sanitizer(settings).sanitize(text)``
      - :func:`turbohtml.clean.sanitize` with a :class:`~turbohtml.clean.Policy`
    - - ``tags``
      - ``Policy.tags``
    - - ``attributes``
      - ``Policy.attributes``
    - - ``add_nofollow``
      - ``Policy.add_link_rel`` (``{"nofollow"}``)
    - - ``sanitize_href`` schemes
      - ``Policy.url_schemes``

.. testcode::

    from turbohtml.clean import sanitize, Policy

    print(
        sanitize(
            '<p>Hi <a href="http://x">l</a></p>',
            Policy(
                tags=frozenset({"p", "a"}),
                attributes={"a": frozenset({"href"})},
                add_link_rel=frozenset({"nofollow"}),
            ),
        )
    )

.. testoutput::

    <p>Hi <a href="http://x" rel="nofollow">l</a></p>

**********
 Pitfalls
**********

- The whitespace normalization and tag-merging html-sanitizer performs (``empty``, ``separate``, ``whitespace``) has no
  direct port; do it with a walk over the returned tree.
- Its ``element_preprocessors``/``element_postprocessors`` hooks have no direct port either. turbohtml's
  ``attribute_filter`` covers value-level rewriting, but structural post-processing is left to a walk over the tree.
