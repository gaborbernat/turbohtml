#############
 Explanation
#############

**************
 Why a C core
**************

Escaping and unescaping sit on hot paths: HTML output escaping runs on every rendered fragment, and unescaping runs on
every chunk of text an HTML parser emits. ``turbohtml`` implements both in C so they run several times faster than an
equivalent pure-Python implementation, with no change in behavior.

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
