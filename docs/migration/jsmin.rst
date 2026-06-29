############
 From jsmin
############

.. image:: https://static.pepy.tech/badge/jsmin/month
    :alt: jsmin monthly downloads
    :target: https://pepy.tech/project/jsmin

`jsmin <https://github.com/tikitu/jsmin>`_ is the Python port of Douglas Crockford's ``jsmin``: a character-level state
machine that removes comments and whitespace. Like the original it does not rename or fold anything, and being a
pure-Python character loop it is slow on large files.

***************
 Why turbohtml
***************

:func:`~turbohtml.minify_js` replaces the call and wins on both axes — it is faster and it shrinks more. turbohtml
parses to an arena AST in C and then renames function-local bindings and folds constants, so it produces smaller output
than jsmin's whitespace-only pass while running an order of magnitude quicker. Inline ``<script>`` minification, which
jsmin leaves entirely to you, is a :class:`~turbohtml.JSMinify` on :class:`~turbohtml.Minify`.

.. code-block:: python

    # jsmin
    from jsmin import jsmin

    jsmin(source)  # Crockford whitespace/comment pass, in Python

    # turbohtml
    import turbohtml

    turbohtml.minify_js(source)  # smaller output, in C

On the vendored library ladder (``python -m bench minify-js``) turbohtml is roughly ten times faster than jsmin and its
output is up to half the size, because jsmin only deletes whitespace where turbohtml renames every local binding and
runs the structural folds.

.. list-table::
    :header-rows: 1
    :widths: 24 19 19 19 19

    - - minify
      - turbohtml time
      - jsmin time
      - turbohtml size
      - jsmin size
    - - underscore (67 kB)
      - 0.6 ms
      - 5.7 ms (9.9x)
      - 19 kB
      - 33 kB (1.7x)
    - - jquery (279 kB)
      - 2.7 ms
      - 23.5 ms (8.7x)
      - 87 kB
      - 138 kB (1.6x)
    - - lodash (531 kB)
      - 2.7 ms
      - 32.8 ms (12.2x)
      - 72 kB
      - 145 kB (2.0x)

Unlike the regex-based :doc:`rjsmin <rjsmin>`, jsmin has no speed advantage to trade for its simpler output, so there is
no case where it beats :func:`~turbohtml.minify_js`.
