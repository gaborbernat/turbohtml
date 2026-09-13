#################
 From langdetect
#################

.. package-meta:: langdetect Mimino666/langdetect

`langdetect <https://github.com/Mimino666/langdetect>`_ identifies a string's natural language. To move that call to
turbohtml, use :func:`turbohtml.detect.detect_language`. Pass visible text to either detector; neither call extracts
text from HTML.

*****************
 Port the result
*****************

.. code-block:: python

    from langdetect import detect

    language = detect("This is an English sentence with enough words to identify its language.")

.. code-block:: python

    from turbohtml.detect import detect_language

    result = detect_language("This is an English sentence with enough words to identify its language.")
    language = result.language

Update consumers of ``language``: langdetect uses labels such as ``"en"`` and ``"zh-cn"``, while turbohtml returns ISO
639-3 codes such as ``"eng"`` and ``"cmn"``. :class:`~turbohtml.detect.LanguageMatch` also includes confidence, script
and an English language name. Model scores and predictions can differ; do not reuse a confidence threshold without
checking it against your own inputs.

*************************
 Handle missing evidence
*************************

langdetect raises ``LangDetectException`` when it finds no usable language features. turbohtml returns a
:class:`~turbohtml.detect.LanguageMatch` with ``language=None`` for empty or symbol-only input. Check that field before
routing a document to a language-specific processor.

:class:`~turbohtml.detect.LanguageDetection` can restrict the candidate languages or apply a confidence floor:

.. code-block:: python

    from turbohtml.detect import LanguageDetection, detect_language

    options = LanguageDetection(allowed=frozenset({"eng", "fra"}))
    result = detect_language("This document should be classified as English or French.", options)

Keep langdetect when you need its ``detect_langs`` ranked probability list or its exact model predictions. turbohtml
returns one match. langdetect supports a fixed ``DetectorFactory.seed`` for repeatable predictions; turbohtml does not
require a random seed.

*************
 Performance
*************

The tables compare steady-state detection of the same strings. They include natural prose, repeated sentences and
explicitly labeled synthetic three-letter combinations. Synthetic inputs measure processing cost, not language accuracy.
Each library keeps its own labels and scores; these timings do not establish equivalent predictions. langdetect loads
its profiles once, uses a fixed seed and raises its text-length limit to process each complete input. Each timed call
creates a detector and returns its ranked probabilities; turbohtml returns one match.

.. bench-table::
    :file: bench/langdetect.json
