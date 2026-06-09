#############
 Explanation
#############

**************
 Why a C core
**************

Escaping and unescaping sit on hot paths: HTML output escaping runs on every rendered fragment, and unescaping runs on
every chunk of text an HTML parser emits. ``turbohtml`` implements both in C so they run several times faster than an
equivalent pure-Python implementation, with no change in behavior.

Measured on CPython 3.14 (a release build, via ``tox -e bench``) against :func:`python:html.escape` and
:func:`python:html.unescape`:

.. list-table::
    :header-rows: 1
    :widths: 12 34 14 14 12

    - - operation
      - input
      - turbohtml
      - stdlib
      - speedup
    - - ``escape``
      - plain prose, no specials
      - 0.35 µs
      - 2.23 µs
      - 6.3x
    - - ``escape``
      - typical HTML markup
      - 4.49 µs
      - 10.5 µs
      - 2.3x
    - - ``escape``
      - special-dense
      - 2.99 µs
      - 26.5 µs
      - 8.9x
    - - ``escape``
      - non-ASCII prose (UCS-2)
      - 0.92 µs
      - 1.88 µs
      - 2.0x
    - - ``escape``
      - astral text (UCS-4)
      - 2.58 µs
      - 2.65 µs
      - 1.0x
    - - ``unescape``
      - named references (dense)
      - 18.1 µs
      - 70.2 µs
      - 3.9x
    - - ``unescape``
      - numeric references (dense)
      - 4.16 µs
      - 76.8 µs
      - 18.5x
    - - ``unescape``
      - mixed named + numeric
      - 8.03 µs
      - 35.2 µs
      - 4.4x
    - - ``unescape``
      - prose, sparse references
      - 3.93 µs
      - 3.87 µs
      - ~1x
    - - ``unescape``
      - non-ASCII with references
      - 9.44 µs
      - 35.2 µs
      - 3.7x

``escape`` gains the most on text that needs little escaping (the SWAR scan skips eight safe bytes at a time);
``unescape`` gains the most on entity-heavy input, especially numeric references, where the standard library pays a
Python call per match. On mostly-plain text ``unescape`` ties :func:`python:html.unescape`, whose regex already
short-circuits and runs in C. Numbers vary with input and hardware; reproduce them with ``tox -e bench``.

Unlike a standard-library accelerator, ``turbohtml`` ships **only** the compiled implementation. :PEP:`399` requires a
pure-Python fallback only for the standard library; as a third-party package distributing per-interpreter wheels,
turbohtml has no need for one, which keeps the surface small.

*************************
 Word-at-a-time scanning
*************************

``escape`` spends most of its time confirming that a string contains nothing that needs escaping. For one-byte strings
it scans eight bytes at a time using SWAR ("SIMD within a register"): it loads eight bytes into a 64-bit integer and
tests every lane for ``&``, ``<``, ``>`` and the quotes with the `has-zero bit trick
<https://graphics.stanford.edu/~seander/bithacks.html#ZeroInWord>`_, advancing eight bytes whenever none match. When
nothing needs escaping the input is returned unchanged. Wider (UCS-2 / UCS-4) strings — see :PEP:`393` for CPython's
string representations — fall back to a straightforward scalar scan. This needs the `PyUnicode buffer API
<https://docs.python.org/3/c-api/unicode.html>`_, which is why turbohtml cannot use the :ref:`Limited API
<python:stable>`.

*******************************
 Matching the standard library
*******************************

``turbohtml`` reproduces the behavior of :func:`python:html.escape` and :func:`python:html.unescape` exactly. ``escape``
uses the same replacements, including ``&#x27;`` for the single quote, and ``unescape`` applies the full `HTML5
character-reference rules <https://html.spec.whatwg.org/multipage/named-characters.html>`_: named references with
longest-prefix matching, numeric references, the Windows-1252 remaps, and the invalid code-point handling that maps to
``U+FFFD`` or the empty string. The test suite checks the C output against the standard library over a large fuzzed
corpus.

****************
 Free-threading
****************

The extension holds no mutable state: inputs are immutable ``str`` objects and the lookup tables are read-only. It
therefore declares free-threading support and a per-interpreter GIL on interpreters new enough to honor those slots, so
it does not force the global lock back on under a free-threaded build. See the `free-threading extension guide
<https://docs.python.org/3/howto/free-threading-extensions.html>`_.
