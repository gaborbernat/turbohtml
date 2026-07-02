################
 From html2text
################

.. package-meta:: html2text Alir3z4/html2text

`html2text <https://github.com/Alir3z4/html2text>`_ converts HTML to Markdown with a streaming ``HTMLParser`` subclass
and a wide option surface, including a ``google_doc`` mode that reads the inline CSS a Google Docs export carries.

***************
 Why turbohtml
***************

:meth:`~turbohtml.Node.to_markdown` replaces an ``html2text`` call with one fully type annotated method on the parsed
tree. It walks the WHATWG tree in C rather than driving a Python ``HTMLParser``, converting a page roughly fifty times
faster while covering the same options, including the Google Docs mode:

.. bench-table::
    :file: bench/html2text.json

*************
 The renames
*************

.. code-block:: python

    # html2text
    import html2text

    html2text.html2text(text)

    # turbohtml
    import turbohtml

    turbohtml.parse(text).to_markdown()

.. testcode::

    print(parse("<h1>Title</h1><p>Some <b>bold</b> text.</p>").to_markdown())

.. testoutput::

    # Title

    Some **bold** text.

The html2text options map onto the grouped :class:`~turbohtml.Markdown` config fields with one name per concept:

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - `html2text <https://github.com/Alir3z4/html2text>`__
      - turbohtml :meth:`~turbohtml.Node.to_markdown`
    - - ``ul_item_mark``
      - ``Markdown.Lists(bullets=...)``
    - - ``emphasis_mark``, ``strong_mark``
      - ``Markdown.Inline(emphasis=..., strong=...)``
    - - ``ignore_emphasis``
      - ``Markdown.Inline(ignore_emphasis=...)``
    - - ``ignore_links``
      - ``Markdown.Links(ignore=...)``
    - - ``skip_internal_links``
      - ``Markdown.Links(skip_internal=...)``
    - - ``inline_links``
      - ``Markdown.Links(style=...)`` (``"inline"``/``"reference"``)
    - - ``ignore_images``, ``images_to_alt``, ``images_as_html``, ``images_with_size``
      - ``Markdown.Images(mode=...)`` (``"markdown"``/``"alt"``/``"ignore"``/``"html"``)
    - - ``default_image_alt``
      - ``Markdown.Images(default_alt=...)``
    - - ``ignore_tables``, ``bypass_tables``
      - ``Markdown.Tables(mode=...)`` (``"markdown"``/``"strip"``/``"html"``)
    - - ``pad_tables``
      - ``Markdown.Tables(pad=...)``
    - - ``body_width``, ``wrap_list_items``, ``wrap_links``
      - ``Markdown.Wrapping(width=..., list_items=..., links=...)``
    - - ``unicode_snob`` (and the ``UNIFIABLE`` table)
      - ``Markdown.Document(transliterate=...)``
    - - ``mark_code``
      - ``Markdown.Code(mark=...)``
    - - ``backquote_code_style``
      - ``Markdown.Code(block_style=...)`` (``"fenced"``/``"indented"``)
    - - ``single_line_break``
      - ``Markdown.Document(block_spacing="single")``
    - - ``baseurl``
      - ``Markdown.Links(base_url=...)``
    - - ``open_quote``, ``close_quote``
      - ``Markdown.Inline(quote_open=..., quote_close=...)``
    - - ``escape_snob``
      - ``Markdown.Escaping(mode="all")``
    - - ``google_doc``
      - ``Markdown.GoogleDoc(enabled=...)`` (or the ``Markdown.google_doc()`` preset)
    - - ``google_list_indent``
      - ``Markdown.GoogleDoc(list_indent=...)``
    - - ``hide_strikethrough``
      - ``Markdown.Inline(hide_strikethrough=...)``

``Markdown.google_doc()`` reads the inline-CSS styling a Google Docs HTML export carries: a ``font-weight`` of ``bold``
or ``700``--``900`` becomes ``strong``, ``font-style:italic`` becomes ``emphasis``, a ``Courier New``/``Consolas``
``font-family`` becomes an inline code span, ``list-style-type`` picks the list marker, and each
``Markdown.GoogleDoc(list_indent=...)`` pixels of ``margin-left`` add one list-nesting level. With
``Markdown.Inline(hide_strikethrough=True)`` a ``text-decoration:line-through`` drops the struck text.

.. testcode::

    from turbohtml import Markdown

    export = '<p><span style="font-weight:700">Quarterly</span> revenue</p>'
    print(parse(export).to_markdown(Markdown.google_doc()))

.. testoutput::

    **Quarterly** revenue

**********
 Pitfalls
**********

- :meth:`~turbohtml.Node.to_markdown` is a method on any node, so convert a subtree by calling it on the element you
  selected (``doc.find("article").to_markdown()``) instead of slicing the HTML string first.
- Layout-aware plain text (the ``inscriptis`` role, :meth:`~turbohtml.Node.to_text`) is a separate method; for the
  unstructured concatenation read :attr:`~turbohtml.Node.text`.
- ``base_url`` does simple prefixing rather than full RFC-3986 URL resolution.
