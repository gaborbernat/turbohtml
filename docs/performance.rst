#############
 Performance
#############

Every number here comes from `pyperf <https://pyperf.readthedocs.io>`_ on CPython 3.14.6 (a release build) on an Apple
M4 running macOS 26. pyperf runs each case in isolated worker processes and reports the mean. The corpora are real
documents: `Project Gutenberg's War and Peace <https://www.gutenberg.org/ebooks/2600>`_, the `WHATWG HTML specification
source <https://github.com/whatwg/html/blob/main/source>`_, the `ECMAScript specification
<https://github.com/tc39/ecma262>`_, and a size-weighted sample of `web-platform-tests
<https://github.com/web-platform-tests/wpt>`_ pages. Reproduce any section with ``tox -e bench <suite>``, where the
suite is one of ``escape``, ``unescape``, ``tokenize``, ``parse``, ``query``, or ``serialize``. Numbers vary with input
and hardware.

***********
 Escaping
***********

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

*************
 Unescaping
*************

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

*************
 Tokenizing
*************

:func:`turbohtml.tokenize` against :class:`python:html.parser.HTMLParser` (driven with no-op handlers) and
`html5lib <https://html5lib.readthedocs.io>`_'s pure-Python tokenizer. The closest case is a document dominated by a
single text node, where the standard library's regex performs one C scan; wherever markup appears, the state machine is
roughly ten times faster.

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

**********
 Parsing
**********

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

***********
 Querying
***********

Each library parses the document once, then the timed call runs one query. ``find`` collects every ``<a>`` element the
way each library reaches for it (turbohtml's :meth:`~turbohtml.Node.find_all`, lxml's XPath ``findall``, selectolax's
and BeautifulSoup's selectors). Because turbohtml resolves the tag name to an interned atom and compares integers
during the walk, it keeps pace with lxml's C XPath engine and runs several times ahead of selectolax and BeautifulSoup.

.. list-table::
    :header-rows: 1
    :widths: 28 18 18 18 18

    - - find every <a>
      - turbohtml
      - lxml
      - selectolax
      - BeautifulSoup
    - - wpt page (4 kB)
      - 0.4 µs
      - 0.5 µs
      - 2.2 µs
      - 6.0 µs
    - - wpt page (9.6 kB)
      - 0.7 µs
      - 0.5 µs
      - 2.6 µs
      - 9.5 µs
    - - wpt page (92 kB)
      - 21.4 µs
      - 23.5 µs
      - 46.7 µs
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
``html``, and BeautifulSoup's ``decode``. turbohtml's SIMD-assisted escape and bulk span copies make it the fastest of
the four.

.. list-table::
    :header-rows: 1
    :widths: 28 18 18 18 18

    - - serialize to HTML
      - turbohtml
      - lxml
      - selectolax
      - BeautifulSoup
    - - wpt page (4 kB)
      - 8.5 µs
      - 18.9 µs
      - 12.5 µs
      - 203 µs
    - - wpt page (9.6 kB)
      - 21.2 µs
      - 51.2 µs
      - 30.0 µs
      - 478 µs
    - - wpt page (92 kB)
      - 200 µs
      - 389 µs
      - 344 µs
      - 5.97 ms
