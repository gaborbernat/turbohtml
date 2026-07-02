####################
 From linkify-it-py
####################

.. package-meta:: linkify-it-py tsutsu3/linkify-it-py

`linkify-it-py <https://github.com/tsutsu3/linkify-it-py>`_ is the pure-Python link scanner `markdown-it-py
<https://github.com/executablebooks/markdown-it-py>`_ pulls in: it scans plain text and returns the link spans it finds,
leaving the caller to turn them into ``<a>`` tags and to skip text that is already markup.

***************
 Why turbohtml
***************

turbohtml does both jobs, fully type annotated: :func:`~turbohtml.clean.linkify` rewrites HTML (and, being HTML-aware,
leaves a URL already inside an ``<a>`` or ``<script>`` alone), while :class:`~turbohtml.clean.Detector` matches spans
the way linkify-it-py's ``match`` does. The candidate scan runs in C, so both the full rewrite and the bare detection
primitives (:meth:`Detector.find <turbohtml.clean.Detector.find>` against ``LinkifyIt().match``, and
:meth:`~turbohtml.clean.Detector.has_link` against ``LinkifyIt().test``) outrun the Python scanner that does strictly
less work. The one close row is ``has_link`` on prose, where ``test`` short-circuits on the first link near the start:

.. bench-table::
    :file: bench/linkify-it-py.json

*************
 The renames
*************

.. code-block:: python

    # linkify-it-py
    from linkify_it import LinkifyIt

    matches = LinkifyIt().match("see https://example.com")
    # [Match(url="https://example.com", index=4, last_index=23, ...)] or None

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - `linkify-it-py <https://github.com/tsutsu3/linkify-it-py>`__
      - turbohtml
    - - ``LinkifyIt().match(text)``
      - :meth:`Detector().find(text) <turbohtml.clean.Detector.find>`
    - - ``Match`` (``index``/``last_index``/``url``/``schema``)
      - :class:`~turbohtml.clean.LinkSpan` (``start``/``end``/``url``/``text``)
    - - ``LinkifyIt().test(text)``
      - :meth:`~turbohtml.clean.Detector.has_link`
    - - ``add(schema, rule)`` (scheme-less schemes)
      - the ``schemes`` argument
    - - ``tlds(...)``
      - the ``tlds`` argument
    - - (rewrite HTML yourself)
      - :func:`~turbohtml.clean.linkify`

.. testcode::

    from turbohtml.clean import Detector

    span = Detector().find("see https://example.com")[0]
    print(span.start, span.end, span.url)

.. testoutput::

    4 23 https://example.com

**********
 Pitfalls
**********

- linkify-it-py reaches further into fuzzy IP and email heuristics; turbohtml covers the common web, ``mailto:``,
  bare-domain, and registered-scheme cases and trades that breadth for being HTML-aware and several times faster.
