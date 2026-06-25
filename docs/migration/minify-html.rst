##################
 From minify-html
##################

.. image:: https://static.pepy.tech/badge/minify-html/month
    :alt: minify-html monthly downloads
    :target: https://pepy.tech/project/minify-html

`minify-html <https://github.com/wilsonzlin/minify-html>`_ is a Rust HTML/CSS/JS minifier with a Python binding;
``minify_html.minify(html, **flags)`` collapses whitespace, drops optional tags, and unquotes attributes, and can also
minify embedded CSS and JavaScript.

***************
 Why turbohtml
***************

:func:`turbohtml.clean.minify` minifies a document with one call over the WHATWG tree turbohtml already builds,
configured by the frozen :class:`~turbohtml.Minify` options object. On the folds the two share (collapsing insignificant
whitespace, omitting the tags the WHATWG rules make optional, dropping redundant attribute quotes, and stripping
comments) it runs about twice as fast, parse included. It leaves embedded CSS and JavaScript untouched, which
minify-html can also shrink.

.. list-table::
    :header-rows: 1
    :widths: 40 30 30

    - - minify a document
      - turbohtml
      - minify-html
    - - daring fireball (10 kB)
      - 32.9 µs
      - 65.8 µs (2.0x)
    - - ars technica (56 kB)
      - 153.1 µs
      - 315.1 µs (2.1x)
    - - mozilla blog (95 kB)
      - 320.6 µs
      - 742.3 µs (2.3x)
    - - whatwg spec (235 kB)
      - 1110.3 µs
      - 1718.6 µs (1.5x)

*************
 The renames
*************

.. code-block:: python

    # minify-html
    import minify_html

    minify_html.minify(html, keep_comments=False)

    # turbohtml
    from turbohtml.clean import minify

    minify(html)

.. testcode::

    from turbohtml.clean import minify

    print(minify("<ul>  <li>  one  </li>  <li>  two  </li>  </ul>"))

.. testoutput::

    <ul> <li> one </li> <li> two </li> </ul>

Each fold is a field on :class:`~turbohtml.Minify`, so a flag becomes one keyword on the options object:

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - minify-html
      - turbohtml :class:`~turbohtml.Minify`
    - - whitespace collapsing (on by default)
      - ``Minify(collapse_whitespace=...)`` (default ``True``)
    - - ``keep_comments`` (``False`` strips them)
      - ``Minify(strip_comments=...)`` (default ``True``)
    - - ``keep_closing_tags``, ``keep_html_and_head_opening_tags``
      - ``Minify(omit_optional_tags=...)`` (default ``True``; set ``False`` to keep every tag)
    - - attribute unquoting
      - ``Minify(unquote_attributes=...)`` (default ``True``)
    - - ``minify_css``, ``minify_js``
      - not supported -- embedded CSS and JavaScript pass through unchanged
    - - ``minify_doctype``
      - the doctype is always normalized to ``<!doctype html>``
    - - ``remove_processing_instructions``
      - the WHATWG algorithm has no processing instructions in the HTML namespace

**********
 Pitfalls
**********

- Every fold is round-trip safe, so minifying is idempotent and the output reparses to the input tree. The two minifiers
  do not produce byte-for-byte identical output, though: turbohtml is the more conservative of the two, so port against
  behavior rather than string equality.
- turbohtml keeps attributes in source order; minify-html sorts them alphabetically.
- turbohtml collapses each whitespace run to one space and keeps a few optional end tags (``</body>``, ``</html>``,
  ``</li>``) that minify-html drops, so its output stays valid and render-safe while running a few bytes larger.
- turbohtml writes boolean attributes in full (``checked="checked"``) and keeps ``&amp;`` where minify-html shortens to
  a bare ``checked`` and ``&``.
- Embedded ``<style>`` and ``<script>`` bodies pass through unchanged; reach for a CSS/JS minifier if you need those
  shrunk.
- ``minify`` parses the input as a full document, so a bare fragment gains the ``<html>``/``<body>`` structure the
  WHATWG algorithm infers; call it on whole pages, not detached fragments.
