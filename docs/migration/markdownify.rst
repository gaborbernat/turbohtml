##################
 From markdownify
##################

.. image:: https://static.pepy.tech/badge/markdownify/month
    :alt: markdownify monthly downloads
    :target: https://pepy.tech/project/markdownify

`markdownify <https://github.com/matthewwithanm/python-markdownify>`_ converts HTML to Markdown by walking a
BeautifulSoup tree, with a per-tag ``convert_<tag>`` override system for customizing the output.

***************
 Why turbohtml
***************

:meth:`~turbohtml.Node.to_markdown` replaces a ``markdownify`` call with one method on the parsed tree. It is fully type
annotated, exposes one keyword per concept, and runs the conversion in C off the WHATWG tree instead of a second Python
walk over a BeautifulSoup tree, so it converts a page two orders of magnitude faster:

.. list-table::
    :header-rows: 1
    :widths: 40 30 30

    - - to Markdown
      - turbohtml
      - markdownify
    - - article (2 KiB)
      - 13 µs
      - 1185 µs (92.4x)
    - - list (4 KiB)
      - 23 µs
      - 2381 µs (103.2x)
    - - table (4 KiB)
      - 26 µs
      - 2825 µs (108.1x)
    - - configured (4 KiB)
      - 28 µs
      - 2560 µs (92.5x)

*************
 The renames
*************

.. code-block:: python

    # markdownify
    from markdownify import markdownify

    markdownify(text)

    # turbohtml
    import turbohtml

    turbohtml.parse(text).to_markdown()

.. testcode::

    print(parse("<h1>Title</h1><p>Some <b>bold</b> text.</p>").to_markdown())

.. testoutput::

    # Title

    Some **bold** text.

The defaults emit opinionated GitHub-Flavored Markdown, and the grouped :class:`~turbohtml.Markdown` config fields cover
markdownify's surface with one name per concept:

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - markdownify
      - turbohtml :meth:`~turbohtml.Node.to_markdown`
    - - ``heading_style`` (``atx``/``atx_closed``/``underlined``)
      - ``Markdown.Headings(style=...)`` (``"atx"``/``"atx_closed"``/``"setext"``)
    - - ``bullets``
      - ``Markdown.Lists(bullets=...)``
    - - ``strong_em_symbol``
      - ``Markdown.Inline(strong=..., emphasis=...)`` (independent, so a superset)
    - - ``sub_symbol``, ``sup_symbol``
      - ``Markdown.Inline(sub=..., sup=...)``
    - - ``escape_asterisks``, ``escape_underscores``
      - ``Markdown.Escaping(asterisks=..., underscores=...)``
    - - ``escape_misc``
      - ``Markdown.Escaping(mode="all")``
    - - ``autolinks``
      - ``Markdown.Links(autolink=...)``
    - - ``default_title``
      - ``Markdown.Links(title=...)``
    - - ``table_infer_header``
      - ``Markdown.Tables(header="first")`` (the default) vs ``"none"``
    - - ``newline_style`` (``spaces``/``backslash``)
      - ``Markdown.Document(line_break=...)`` (``"spaces"``/``"backslash"``)
    - - ``strip_document``
      - ``Markdown.Document(trim=...)`` (``"strip"``/``"lstrip"``/``"rstrip"``/``"none"``)
    - - ``code_language``
      - ``Markdown.Code(language=...)``
    - - ``strip``, ``convert``
      - ``Markdown(strip=...)``, ``Markdown(convert=...)`` (mutually exclusive tag filters)
    - - ``convert_<tag>`` overrides
      - ``Markdown(converters=...)`` argument

**********
 Pitfalls
**********

- The bold and italic markers are independent (``Markdown.Inline(strong=...)`` and ``Markdown.Inline(emphasis=...)``),
  where markdownify derives both from one ``strong_em_symbol``; set both to reproduce its behavior.
- :meth:`~turbohtml.Node.to_markdown` is a method on any node, so convert a subtree by calling it on the element you
  selected (``doc.find("article").to_markdown()``) instead of slicing the HTML string first.
- markdownify's parser-selection options (``bs4_options``) are dropped, since turbohtml always runs the WHATWG
  algorithm.
- ``Markdown.Links(base_url=...)`` does simple prefixing rather than full RFC-3986 URL resolution.
