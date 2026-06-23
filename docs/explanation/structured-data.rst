############################
 Structured-data extraction
############################

:meth:`~turbohtml.Document.structured_data` answers the scraping question ``extruct`` and ``metadata_parser`` exist for:
what machine-readable metadata does this page embed? It pulls JSON-LD, Microdata, and OpenGraph/Twitter card metadata in
one walk, with the per-format helpers :meth:`~turbohtml.Document.json_ld`, :meth:`~turbohtml.Document.opengraph`, and
:meth:`~turbohtml.Document.microdata` beside it. The combined result is a frozen :class:`~turbohtml.StructuredData`
record with a stable five-field shape -- ``json_ld``, ``microdata``, ``opengraph``, plus ``microformats`` and ``rdfa``
reserved for a later phase -- so code that reads it does not break when those formats land. The records hold no
reference back into the tree, so they outlive the document they came from.

*********************
 Where the work runs
*********************

The division of labor is the same one the rest of the read path follows: the *locating* runs in C and the only genuinely
Python step stays in Python. A pure-C pass under the per-tree critical section walks the document once per format,
gathering the ``itemscope``/``itemprop``/``itemtype`` structure into nested :class:`~turbohtml.MicrodataItem` records
and the OpenGraph and Twitter ``<meta>`` pairs into a flat mapping, all holding no reference back into the tree. JSON-LD
is the exception that proves the rule: the C walk gathers the verbatim text of each ``<script
type="application/ld+json">`` block into a list of strings, then the critical section is released and a thin facade
parses them with the standard library :mod:`json`. The JSON grammar is not reinvented in C, and the parse never touches
the tree, so it cannot race a concurrent mutation -- the snapshot-then-parse split is what keeps the Python call off the
live structure. A block that is not valid JSON is skipped rather than raising, the robust default for scraping a page
whose markup the author did not validate.

*******************************
 Microdata, OpenGraph, Twitter
*******************************

Microdata follows the HTML value algorithm: a property's value is the nested item dict when the element carries
``itemscope``, otherwise its ``content`` for a meta element, the relevant URL attribute for the link and media tags,
``datetime`` (or text) for a time element, and the element's text content elsewhere. Only top-level items -- an element
with ``itemscope`` and no ``itemprop``, so it is not a property of another item -- become list entries; a nested item is
reached through its parent's ``properties``. OpenGraph and Twitter share one mapping because pages mix the ``property``
and ``name`` attributes freely; when a key repeats, the last occurrence wins.
