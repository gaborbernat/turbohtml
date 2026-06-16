#############
 Performance
#############

Every number here comes from `pyperf <https://pyperf.readthedocs.io>`_ on CPython 3.14.6 (a release build) on an Apple
M4 running macOS 26. pyperf runs each case in isolated worker processes and reports the mean. The corpora are real
documents: `Project Gutenberg's War and Peace <https://www.gutenberg.org/ebooks/2600>`_, the `WHATWG HTML specification
source <https://github.com/whatwg/html/blob/main/source>`_, the `ECMAScript specification
<https://github.com/tc39/ecma262>`_, and a size-weighted sample of `web-platform-tests
<https://github.com/web-platform-tests/wpt>`_ pages. Reproduce any section with ``tox -e bench <suite>``, where the
suite is one of ``escape``, ``unescape``, ``tokenize``, ``parse``, ``query``, ``serialize``, ``build``, or ``edit``.
Numbers vary with input and hardware.

**********
 Escaping
**********

:func:`turbohtml.escape` against the standard library's :func:`python:html.escape`. It gains the most on text that needs
little escaping, where the SIMD scan classifies sixteen bytes at a time and copies clean stretches in bulk; the gap
narrows on tiny strings, where call overhead dominates.

.. list-table::
    :header-rows: 1
    :widths: 40 20 20

    - - input
      - turbohtml
      - html.escape
    - - tiny plain (64 B)
      - 0.04 µs
      - 0.11 µs
    - - medium markup (4 KiB)
      - 2.25 µs
      - 7.17 µs
    - - no-op prose (4 MiB)
      - 0.11 ms
      - 2.51 ms
    - - book text (3 MiB)
      - 0.66 ms
      - 2.56 ms
    - - book HTML (4 MiB)
      - 1.25 ms
      - 4.54 ms
    - - spec HTML, dense (4 MiB)
      - 4.93 ms
      - 12.8 ms
    - - UCS-2 plain (4 MiB)
      - 0.70 ms
      - 2.41 ms
    - - UCS-2 markup (4 MiB)
      - 3.33 ms
      - 10.9 ms
    - - UCS-4 plain (4 MiB)
      - 0.91 ms
      - 5.29 ms
    - - UCS-4 markup (4 MiB)
      - 3.95 ms
      - 19.3 ms

************
 Unescaping
************

:func:`turbohtml.unescape` against :func:`python:html.unescape`. It gains the most on entity-heavy input, where the
standard library pays a Python call per match; turbohtml hops between ``&`` occurrences and bulk-copies the clean spans
between references.

.. list-table::
    :header-rows: 1
    :widths: 40 20 20

    - - input
      - turbohtml
      - html.unescape
    - - tiny plain (64 B)
      - 0.02 µs
      - 0.03 µs
    - - medium dense refs (4 KiB)
      - 8.22 µs
      - 69.0 µs
    - - numeric refs (4 KiB)
      - 5.83 µs
      - 78.7 µs
    - - book HTML, real refs (4 MiB)
      - 2.44 ms
      - 7.87 ms
    - - escaped book HTML (5 MiB)
      - 1.90 ms
      - 19.5 ms
    - - dense refs (4 MiB)
      - 9.89 ms
      - 73.0 ms
    - - UCS-2 refs (4 MiB)
      - 2.51 ms
      - 18.1 ms

************
 Tokenizing
************

:func:`turbohtml.tokenize` against :class:`python:html.parser.HTMLParser` (driven with no-op handlers) and `html5lib
<https://html5lib.readthedocs.io>`_'s pure-Python tokenizer. The closest case is a document dominated by a single text
node, where the standard library's regex performs one C scan; wherever markup appears, the state machine is roughly ten
times faster.

.. list-table::
    :header-rows: 1
    :widths: 28 18 18 18

    - - input
      - turbohtml
      - html.parser
      - html5lib
    - - typical markup
      - 29.3 µs
      - 435 µs
      - 810 µs
    - - text-heavy prose
      - 0.54 µs
      - 2.8 µs
      - 143 µs
    - - attribute-heavy
      - 19.2 µs
      - 298 µs
      - 807 µs
    - - script-heavy
      - 12.1 µs
      - 156 µs
      - 488 µs
    - - entity-heavy
      - 20.4 µs
      - 197 µs
      - 1.20 ms
    - - wpt page (0.6 kB)
      - 1.4 µs
      - 17.5 µs
      - 47.7 µs
    - - wpt page (4 kB)
      - 12.1 µs
      - 165 µs
      - 422 µs
    - - wpt page (9.6 kB)
      - 29.2 µs
      - 360 µs
      - 1.16 ms
    - - wpt page (92 kB)
      - 324 µs
      - 4.03 ms
      - 8.93 ms
    - - wpt page, CJK (124 kB)
      - 584 µs
      - 8.45 ms
      - 22.6 ms
    - - whatwg spec (235 kB)
      - 645 µs
      - 7.39 ms
      - 19.3 ms
    - - ecmascript spec (3 MB)
      - 5.88 ms
      - 55.0 ms
      - 181 ms
    - - whatwg spec source (7.9 MB)
      - 35.0 ms
      - 389 ms
      - 853 ms

*********
 Parsing
*********

:func:`turbohtml.parse` builds a full WHATWG document tree, against the other Python tree builders: `lxml
<https://lxml.de>`_, `selectolax <https://github.com/rushter/selectolax>`_ (lexbor), `BeautifulSoup
<https://www.crummy.com/software/BeautifulSoup/bs4/doc/>`_ over ``html.parser``, and html5lib. turbohtml runs roughly
two to five times faster than the C parsers and 30 to 80 times faster than the pure-Python ones, while building the
WHATWG tree that lxml's libxml2 does not.

.. list-table::
    :header-rows: 1
    :widths: 26 13 12 12 14 12

    - - input
      - turbohtml
      - lxml
      - selectolax
      - BeautifulSoup
      - html5lib
    - - wpt page (0.6 kB)
      - 1.3 µs
      - 3.3 µs
      - 6.8 µs
      - 61.6 µs
      - 101 µs
    - - wpt page (4 kB)
      - 10.6 µs
      - 26.7 µs
      - 42.1 µs
      - 443 µs
      - 616 µs
    - - wpt page (9.6 kB)
      - 25.4 µs
      - 72.6 µs
      - 107 µs
      - 849 µs
      - 1.44 ms
    - - wpt page (92 kB)
      - 268 µs
      - 629 µs
      - 920 µs
      - 15.5 ms
      - 17.0 ms
    - - wpt page, CJK (124 kB)
      - 483 µs
      - 1.44 ms
      - 2.30 ms
      - 21.5 ms
      - 28.0 ms
    - - whatwg spec (235 kB)
      - 504 µs
      - 1.23 ms
      - 1.78 ms
      - 26.4 ms
      - 31.9 ms
    - - ecmascript spec (3 MB)
      - 4.42 ms
      - 17.5 ms
      - 15.8 ms
      - 183 ms
      - 254 ms
    - - whatwg spec source (7.9 MB)
      - 27.6 ms
      - 83.8 ms
      - 94.8 ms
      - 1.66 s
      - 1.73 s

**********
 Querying
**********

Each library parses the document once, then the timed call runs one query. ``find`` collects every ``<a>`` element the
way each library reaches for it (turbohtml's :meth:`~turbohtml.Node.find_all`, lxml's XPath ``findall``, selectolax's
and BeautifulSoup's selectors). A tag-only query resolves the name to an interned atom and walks the subtree comparing
integers, with no per-element string built and no matcher dispatch, so it runs ahead of lxml's C XPath engine and
several times ahead of selectolax and BeautifulSoup.

.. list-table::
    :header-rows: 1
    :widths: 28 18 18 18 18

    - - find every <a>
      - turbohtml
      - lxml
      - selectolax
      - BeautifulSoup
    - - wpt page (4 kB)
      - 0.2 µs
      - 0.5 µs
      - 2.2 µs
      - 5.8 µs
    - - wpt page (9.6 kB)
      - 0.3 µs
      - 0.5 µs
      - 2.6 µs
      - 9.5 µs
    - - wpt page (92 kB)
      - 11.5 µs
      - 23.5 µs
      - 45.8 µs
      - 206 µs

``select`` runs the CSS selector ``div a[href]`` (turbohtml's :meth:`~turbohtml.Node.select`, lxml's ``cssselect``,
selectolax's ``css``, BeautifulSoup's soupsieve). Because turbohtml compiles the selector against the tree once and then
compares interned integer atoms, it runs from twice to forty times faster than lxml and over a hundred times faster than
BeautifulSoup.

.. list-table::
    :header-rows: 1
    :widths: 28 18 18 18 18

    - - select ``div a[href]``
      - turbohtml
      - lxml
      - selectolax
      - BeautifulSoup
    - - wpt page (4 kB)
      - 0.4 µs
      - 15.6 µs
      - 2.5 µs
      - 42.9 µs
    - - wpt page (9.6 kB)
      - 0.5 µs
      - 16.4 µs
      - 3.0 µs
      - 65.0 µs
    - - wpt page (92 kB)
      - 14.2 µs
      - 33.6 µs
      - 45.8 µs
      - 2.13 ms

*************
 Serializing
*************

Serializing a parsed document back to HTML: turbohtml's :attr:`~turbohtml.Node.html`, lxml's ``tostring``, selectolax's
``html``, and BeautifulSoup's ``decode``. turbohtml scans each text run for the next character that needs escaping and
bulk-copies the clean spans, so it serializes faster than lxml, selectolax, and BeautifulSoup.

.. list-table::
    :header-rows: 1
    :widths: 28 18 18 18 18

    - - serialize to HTML
      - turbohtml
      - lxml
      - selectolax
      - BeautifulSoup
    - - wpt page (4 kB)
      - 4.6 µs
      - 18.6 µs
      - 12.3 µs
      - 197 µs
    - - wpt page (9.6 kB)
      - 12.9 µs
      - 50.9 µs
      - 29.8 µs
      - 471 µs
    - - wpt page (92 kB)
      - 151 µs
      - 383 µs
      - 340 µs
      - 5.94 ms

**********
 Building
**********

The write path: construct a ``<ul>`` of ``N`` ``<li>`` rows from scratch (each with a ``class``, a ``data`` attribute,
and a text child), then serialize it, the work an editor or template engine does. turbohtml's arena allocation and
interned attribute names make construction cheaper than lxml's libxml2 nodes and far cheaper than BeautifulSoup's Python
objects. selectolax is parse-only, so it has no entry.

.. list-table::
    :header-rows: 1
    :widths: 28 24 24 24

    - - build a list
      - turbohtml
      - lxml
      - BeautifulSoup
    - - 100 rows
      - 54.8 µs
      - 143 µs
      - 720 µs
    - - 1000 rows
      - 557 µs
      - 1.38 ms
      - 7.43 ms
    - - 10000 rows
      - 5.70 ms
      - 13.2 ms
      - 77.0 ms

*********
 Editing
*********

Editing a parsed tree: tag every ``<a>`` with ``rel="nofollow"``, a link-rewriting pass. Each library parses once
outside the timed region, then the timed call walks its links and sets the attribute (turbohtml through the live
:attr:`~turbohtml.Element.attrs` mapping, lxml through ``Element.set``, BeautifulSoup through item assignment).
selectolax mutation is limited, so it has no entry.

.. list-table::
    :header-rows: 1
    :widths: 28 24 24 24

    - - tag every link
      - turbohtml
      - lxml
      - BeautifulSoup
    - - wpt page (4 kB)
      - 243 ns
      - 772 ns
      - 5.98 µs
    - - wpt page (9.6 kB)
      - 368 ns
      - 766 ns
      - 10.0 µs
    - - wpt page (92 kB)
      - 17.5 µs
      - 41.5 µs
      - 210 µs
