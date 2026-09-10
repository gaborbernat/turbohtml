#############
 Performance
#############

.. warning::

    The September 8 audit measurements remain provisional. The first two passes checked CPU headroom without enforcing
    memory-pressure or swap limits. The third and fourth passes enforced those limits, but some before/after comparisons
    used different interpreter builds. Those comparisons need repeats with one interpreter before they establish a speed
    improvement. The normalization, attribute, equality, translation, and numbering tables below use matched interpreter
    and binary configurations.

These `pyperf <https://pyperf.readthedocs.io>`_ tables use CPython 3.14 on an Apple M4 running macOS 26. The September
8, 2026 audit refresh uses CPython 3.14.7; older tables use 3.14.6. Each cell reports the mean and run-to-run standard
deviation as ``±N%``. Compare gaps against that spread. The published turbohtml measurements use PGO/LTO release builds
unless a section states otherwise; the default benchmark command builds a plain wheel for development.

The harness creates an isolated ``uv`` environment for each library. Mutation cases rebuild their input before each
timed iteration, with setup excluded from the measurement. Read operations reuse a parsed tree. The corpora include
`Project Gutenberg's War and Peace <https://www.gutenberg.org/ebooks/2600>`_, the `WHATWG HTML specification source
<https://github.com/whatwg/html/blob/main/source>`_, the `ECMAScript specification <https://github.com/tc39/ecma262>`_,
`web-platform-tests <https://github.com/web-platform-tests/wpt>`_ pages, and saved blog, news, and product pages from
`mozilla/readability <https://github.com/mozilla/readability>`_. Synthetic scaling cases vary sibling count, tree depth,
and text length. Their results apply to those inputs and sizes.

Reproduce a table with ``tox -e bench -- --pgo <operation>``. You can also select a package, ``core`` for turbohtml, or
``all``. Pass pyperf options such as ``--rigorous`` through the same command; CPU affinity and system tuning depend on
platform support. Most cases time one call. The ``build`` and ``build-e`` cases construct and serialize a tree;
``construct`` and ``emit`` measure those steps apart.

The ``collapse-whitespace``, ``strip-comments``, and ``transform-tree`` operations time DOM transformations with fresh
input trees prepared outside each measurement. ``serialize-inner`` measures configured child serialization. These
operations also have CodSpeed cases in the shared registry. Use the same release build and corpus for comparisons;
report composition overhead separately from changes in the transformed workflow. Whitespace collapse also covers 1 MiB
unchanged text and whitespace-heavy text in the benchmark suite and CodSpeed.

To refresh these tables, run the sweep into a scratch directory and let the generators rewrite the committed feeds; the
harness names its output for the operation, which is not what this guide calls its tables, so never copy the files
across by hand:

::

    tox -e bench -- --pgo --table-json /tmp/feeds all
    python -m bench.docs_feeds /tmp/feeds docs/development/bench
    python -m bench.migration /tmp/feeds docs/migration/bench docs tools/bench/competitors

**********
 Escaping
**********

:func:`turbohtml.escape` against the standard library's :func:`python:html.escape` (the ``stdlib`` column), dominate's
text escape, and the nh3 ammonia binding. It gains the most on text that needs little escaping, where the SIMD scan
classifies sixteen bytes at a time and copies clean stretches in bulk: on 4 MiB of no-op prose it runs 22 times faster
than html.escape and 65 times faster than nh3. The gap narrows to two to four times on tiny strings and escape-dense
markup, where call overhead and the escaping itself dominate.

.. bench-table::
    :file: bench/escaping.json

*******************
 Markup (escaping)
*******************

:func:`turbohtml.migration.markupsafe.escape` against `markupsafe <https://markupsafe.palletsprojects.com>`_'s own C
escape, both returning a ``Markup``. The inputs are the small, mostly-clean strings a template engine interpolates under
autoescape, markupsafe's hottest path. turbohtml builds the safe string in C in a single call, where markupsafe pays a
Python ``escape`` frame and ``Markup`` construction per call, so it runs two and a half to nearly four times faster
across the clean and escape-heavy inputs.

.. bench-table::
    :file: bench/markup-escaping.json

The other ``Markup`` operations race markupsafe's own ``Markup`` of the same method. ``striptags`` and ``unescape`` run
on turbohtml's tokenizer and HTML5 reference resolution where markupsafe scans with a regex, and ``format`` and ``join``
escape each untrusted operand through the same C ``escape``.

.. bench-table::
    :file: bench/markup-escaping-2.json

*********
 Linkify
*********

:func:`turbohtml.clean.linkify` against `bleach <https://bleach.readthedocs.io>`_'s ``linkify``, the HTML-aware
linkifier it succeeds, and `lxml-html-clean <https://github.com/fedora-python/lxml_html_clean>`_'s ``autolink``. All
three parse the HTML and rewrite it. turbohtml's C candidate scan and its own tree carry it past bleach's html5lib pass
by six to twenty times. It leads lxml's autolink on the comment and 4 KiB markup inputs and trails it on the plain 1 KiB
prose row (0.6x), though that row is not a like-for-like comparison: ``autolink`` only rewrites URLs already inside
markup and never linkifies an email address, so on plain prose it produces no links at all where turbohtml produces
thirty. Its figure there is the cost of finding nothing.

.. bench-table::
    :file: bench/linkify.json

A single C walk creates wrappers only for eligible text and anchor targets; Python no longer visits every node. CodSpeed
tracks a text-heavy tree, 2,000 small text nodes, and 2,000 empty elements. Separate cases cover skip-tag pruning and
callback-heavy HTML. Callbacks run in document order after target collection releases the tree lock.

The detection primitive on its own, :meth:`turbohtml.clean.LinkDetector.find` against ``LinkifyIt().match`` and
:meth:`~turbohtml.clean.LinkDetector.has_link` against ``LinkifyIt().test``, scans a run of plain text without rewriting
HTML. Both libraries stop on the first valid match; turbohtml allocates no span list. The large-tail case starts with a
link followed by 220 KiB of prose to catch a return to full-input scanning.

.. bench-table::
    :file: bench/linkify-2.json

Phone-number detection, :class:`~turbohtml.clean.LinkDetector` with a :class:`~turbohtml.clean.PhoneNumbers` setting
against `phonenumbers <https://github.com/daviddrysdale/python-phonenumbers>`_'s ``PhoneNumberMatcher``, both with the
United States as the default region. The build compiles the numbering plans to automata, so a candidate is a table walk
per digit where the port runs the library's regular expressions over each one: 36x faster on the mixed corpus, 22x to
33x on prose with a few numbers, and 54x to 107x on the digit-heavy inputs where those expressions retry the most. The
eight-region rows give turbohtml eight fallback regions and the matcher its first; the adversarial rows are 21-group
digit runs that form no number, the shape that costs the most splits; the prose rows with no digits measure the trigger
scan alone (8x to 9x, the narrowest rows).

.. bench-table::
    :file: bench/linkify-3.json

:meth:`PhoneNumber.parse <turbohtml.clean.PhoneNumber.parse>` against ``phonenumbers.parse`` followed by
``is_valid_number`` (``is_possible_number`` on the possible row), over twenty held numbers from twenty regions, each in
a written form of its own: national with the prefix, international, with an extension, bracketed. The port normalizes
the string, strips prefixes and matches the plan's regular expressions one type at a time; turbohtml runs the same
recognizer the scanner uses over the one string, 7x faster (5x on the possible row).

.. bench-table::
    :file: bench/linkify-4.json

:meth:`PhoneNumber.format <turbohtml.clean.PhoneNumber.format>` against ``format_number`` over the same twenty numbers,
parsed once outside the timed loop, one layout per row. The port picks the number format by running its leading-digits
and pattern expressions and substitutes the groups with a regular-expression replacement; turbohtml walks one
leading-digits automaton per candidate format and splits the digits by the group bounds the generator recorded, 14x to
18x faster; E.164 joins a few strings on both sides and is the narrowest row at 2x.

.. bench-table::
    :file: bench/linkify-5.json

**********
 Sanitize
**********

:func:`turbohtml.clean.sanitize` against four sanitizers. Three share its allowlist model, where only listed tags and
attributes survive, so a vector nobody anticipated is dropped by default: `nh3 <https://nh3.readthedocs.io>`_ (the Rust
ammonia binding), `bleach <https://bleach.readthedocs.io>`_ (its end-of-life predecessor, on html5lib), and
`html-sanitizer <https://github.com/matthiask/html-sanitizer>`_ (an allowlist over lxml). The fourth, `lxml-html-clean
<https://github.com/fedora-python/lxml_html_clean>`_ (the externalized ``lxml.html.clean.Cleaner``), is a blocklist: it
strips the constructs it knows are dangerous and lets the rest through, a model lxml itself flagged as hard to keep
safe. The inputs are realistic user content with a few disallowed tags and a dangerous attribute mixed in. turbohtml
runs the whole filtering walk in C and leads every alternative, but the model matters more than the microseconds. Prefer
an allowlist, since a blocklist passes anything it did not think to name.

.. bench-table::
    :file: bench/sanitize.json

Template-safe sanitizing (``Policy.strip_template_markers``, collapsing ``{{ }}``/``${ }``/``<% %>`` so the output
cannot re-inject through a template engine) has no allowlist-sanitizer analog in Python; the reference is DOMPurify's
``SAFE_FOR_TEMPLATES``, which runs in JavaScript. Reaching it from Python means shelling out to Node, where each call
spins up a DOM before it sanitizes, so the figure below is that end-to-end per-document cost, not a pure-algorithm
comparison. turbohtml folds the same transform into its C walk and pays neither the process nor the DOM.

.. bench-table::
    :file: bench/sanitize-templates.json

**********
 Markdown
**********

:meth:`turbohtml.Node.to_markdown` against `markdownify <https://github.com/matthewwithanm/python-markdownify>`_ (on
BeautifulSoup) and `html2text <https://github.com/Alir3z4/html2text>`_ (a streaming ``HTMLParser`` subclass). The
turbohtml adapter reuses a cached parsed document and times its Markdown conversion. The markdownify and html2text
adapters parse and convert the HTML string on each call. These timings therefore include different parsing costs. The
``configured`` row enables underscore emphasis, reference links, padded tables, and full escaping.

.. bench-table::
    :file: bench/markdown.json

The ``google_doc`` row reads the inline-CSS styling a Google Docs export carries (html2text's google_doc mode) and runs
32 times faster; markdownify has no equivalent.

The long-run cases convert 8,192 asterisks or ASCII letters. Turbohtml and markdownify use default escaping; html2text
enables ``escape_snob`` to preserve the asterisks as literal characters. The outputs match apart from a trailing
newline. Word wrapping needs the next word's length only when it may replace a pending space with a line break. Skipping
that scan elsewhere avoids rescanning the remaining suffix after each escaped character. CodSpeed tracks both cases.

Matched CPython 3.14.7 release builds without PGO or LTO reduced the asterisk case from 8,652.190 to 43.807 µs (99.49%
faster). The letter control fell from 13.493 to 10.782 µs (20.09% faster), with 7–9% sample spread. All eight runs
passed CPU-headroom and memory-pressure guards. The four competitor measurements also passed those guards. These rows
reuse the parsed turbohtml document; markdownify and html2text parse and convert each timed call.

.. bench-table::
    :file: bench/markdown-runs.json

The wrapping cases reuse a parsed document containing 10,000 short words, with widths of 8,192 and 80 code points. The
converter tracks the last checked output position so a wrapping decision scans only the newly appended text. Converter
callbacks save and restore that position when they render children into a temporary buffer.

Matched CPython 3.14.7 release builds without PGO or LTO reduced the wide case from 9,803.964 to 125.627 µs (98.72%
faster). The 80-column control fell from 267.743 to 129.001 µs (51.82% faster). Candidate spread was 5.31% for wide
wrapping and 3.07% at 80 columns. All eight comparisons passed CPU-headroom and memory-pressure guards. CodSpeed tracks
both widths; document parsing and option construction happen outside the timer. The table uses separate measurements of
the shared adapter, including its cached-setup lookup.

.. bench-table::
    :file: bench/markdown-wrap.json

*****************
 Structured data
*****************

Compare :meth:`turbohtml.Document.structured_data` with `extruct <https://github.com/scrapinghub/extruct>`_ on a product
page containing JSON-LD, Microdata, and OpenGraph. Both operations include parsing. extruct uses lxml and a separate
extractor per syntax; turbohtml uses its WHATWG parser and C extractors, returning a :class:`~turbohtml.StructuredData`
record. turbohtml snapshots the tree before extraction to preserve consistent results when Python constructors call back
into the document.

.. bench-table::
    :file: bench/structured-data.json

********
 Tables
********

:meth:`turbohtml.Node.tables` and :meth:`turbohtml.Element.records` against `pandas <https://pandas.pydata.org>`_'s
``read_html``, the one-call table reader scrapers reach for. Both parse the HTML and extract every ``<table>``,
resolving ``rowspan`` and ``colspan`` into a rectangular grid; ``read_html`` returns a ``DataFrame`` per table and pulls
in NumPy, where turbohtml runs the cell-grid walk in C and hands back plain ``list`` and ``dict`` objects with no added
dependency. The ``rows`` row times :meth:`~turbohtml.Node.tables` (every table as ``list[list[str]]``) and the
``records`` row times :meth:`~turbohtml.Element.records` (the first table keyed by its header), each over a four-column
table of 10, 100, and 1,000 rows. The single C pass leads from roughly thirty times on the thousand-row table to over a
hundred and sixty on the ten-row table, where pandas pays its fixed per-frame construction cost.

.. bench-table::
    :file: bench/tables.json

********************
 Article extraction
********************

Compare :meth:`turbohtml.Node.article` with `trafilatura <https://trafilatura.readthedocs.io>`_, `readability-lxml
<https://github.com/buriy/python-readability>`_, `newspaper3k <https://newspaper.readthedocs.io>`_, `goose3
<https://goose3.readthedocs.io>`_, `readabilipy <https://readabilipy.readthedocs.io>`_, and `news-please
<https://github.com/fhamborg/news-please>`_. turbohtml scores candidates and extracts their content in C. trafilatura,
newspaper3k, goose3, and news-please collect page metadata as well. readabilipy's Python mode uses html5lib and
BeautifulSoup to clean content without scoring; news-please combines several extractors. The inputs include navigation
and a footer around the article, so the measured cost includes processing boilerplate.

.. bench-table::
    :file: bench/article-extraction.json

****************************
 Boilerplate classification
****************************

:func:`turbohtml.extract.boilerplate` against `justext <https://github.com/miso-belica/jusText>`_ and `boilerpy3
<https://github.com/jmriebold/BoilerPy3>`_, the per-block boilerplate classifiers. All three segment the page into units
and mark each good or boilerplate; justext scores every paragraph in Python over an lxml tree (length, link density,
stopword density), boilerpy3 classifies the blocks of its own SAX stream with boilerpipe's rules, and turbohtml scores
the tree once in C and classifies the units in a thin Python layer. The inputs are the article-extraction pages, so the
navigation and footer each classifier must reject are part of the measured cost.

.. bench-table::
    :file: bench/boilerplate-classification.json

*****************
 Date extraction
*****************

:func:`turbohtml.extract.dates` against `htmldate <https://htmldate.readthedocs.io>`_, the standalone publication-date
finder, and the article extractors trafilatura, newspaper3k, goose3, and news-please that surface a date beside the body
text. All read the same signals -- publication/modification ``<meta>`` tags, JSON-LD, ``<time>`` elements, and a date in
the URL -- and are parse-bound; htmldate builds an lxml tree, turbohtml the WHATWG tree. turbohtml's early-exit over the
structured signals runs 2.9 to 3.3 times faster than htmldate on the real pages and 20 to 24 times faster than
trafilatura. The synthetic ``100 meta candidates`` row -- a page stacked with a hundred date-like ``<meta>`` tags -- was
the one case turbohtml lost, since it weighed every candidate where htmldate and trafilatura stopped early; moving that
weighing into C turns it around, and turbohtml now leads the row too, 3.0 times over htmldate and 4.1 times over
trafilatura.

.. bench-table::
    :file: bench/date-extraction.json

************
 Unescaping
************

:func:`turbohtml.unescape` against :func:`python:html.unescape` (the ``stdlib`` column), `w3lib
<https://github.com/scrapy/w3lib>`_'s ``replace_entities``, the Scrapy helper that resolves the same references, and
dominate's ``util.unescape``. It gains the most on entity-heavy input, where the standard library pays a Python call per
match and w3lib runs a regular-expression substitution with a Python callback per match; turbohtml hops between ``&``
occurrences in C and bulk-copies the clean spans between references, so it leads html.unescape by up to 16 times and
w3lib by up to 22 times on the reference-dense inputs. dominate sits in that same range on the small strings, but its
scan turns multi-megabyte input into whole seconds, trailing by 525 times on the 4 MiB book and past 2,600 on the
escaped copy.

.. bench-table::
    :file: bench/unescaping.json

************
 Tokenizing
************

:func:`turbohtml.tokenize` against :class:`python:html.parser.HTMLParser` (the ``stdlib`` column, driven with no-op
handlers) and `html5lib <https://html5lib.readthedocs.io>`_'s pure-Python tokenizer. The closest case is a document
dominated by a single text node (the ``text-heavy prose`` row, 4.8x), where the standard library's regex performs one C
scan; wherever markup appears, the state machine runs roughly eight to sixteen times faster than html.parser and 22 to
240 times faster than html5lib.

.. bench-table::
    :file: bench/tokenizing.json

*********
 Parsing
*********

:func:`turbohtml.parse` builds a full WHATWG document tree, against the other Python tree builders: `lxml
<https://lxml.de>`_ and `parsel <https://parsel.readthedocs.io>`_ and `pyquery <https://github.com/gawel/pyquery>`_ (all
over libxml2), `selectolax <https://github.com/rushter/selectolax>`_ and `resiliparse
<https://github.com/chatnoir-eu/chatnoir-resiliparse>`_ (both wrapping `lexbor <https://lexbor.com>`_), `html5-parser
<https://html5-parser.readthedocs.io>`_ (the C gumbo binding), `BeautifulSoup
<https://www.crummy.com/software/BeautifulSoup/bs4/doc/>`_ over each of its tree builders, and html5lib. turbohtml leads
resiliparse by 1.2 to 3.4 times, runs 2.7 to 6.2 times faster than lxml, parsel, pyquery, and selectolax, 4.9 to 12.6
times faster than html5-parser, and 31 to 99 times faster than html5lib and BeautifulSoup, while building the WHATWG
tree that lxml's libxml2 does not.

resiliparse stays closest because its ``HTMLTree.parse`` is a thin call straight into lexbor's native tree, while
selectolax wraps that same engine behind a heavier object layer; the comparison here is parsing only. resiliparse's
wider toolkit, boilerplate and main-content extraction, language detection, and the encoding and archive utilities it
ships for large-scale web-crawl processing, sits outside turbohtml's scope. html5-parser wraps `gumbo
<https://github.com/google/gumbo-parser>`_, the C WHATWG parser Google released; it is read-oriented and archived
upstream, and it trails by five to thirteen times above. turbohtml is the maintained, mutable, typed alternative to that
lineage.

.. bench-table::
    :file: bench/parsing.json

The formatting-ancestor cases parse 1,000 ``samp`` elements inside one ``b``, with either 256 intervening ``span``
elements or none. A validated stack-position hint avoids searching the open-element stack for the same formatting
ancestor on each token. Matched local runs reduced full-parse time by 37% at depth 256; the shallow control changed by
1.4%. Both cases use ASCII input with source locations disabled and include document cleanup. CodSpeed tracks both.

Parsel takes 225.1 µs on the deep input, compared with turbohtml's 302.0 µs. Resiliparse takes 267.1 µs on the deep
input and 79.2 µs on the shallow input, ahead of turbohtml's 87.4 µs. The default lxml and pyquery parsers truncate the
deep input, dropping all 1,000 ``samp`` elements; those cells have no timing. Other measured parsers preserve the
complete tree. The html5-parser environment could not import because its libxml2 version differs from lxml's.

.. bench-table::
    :file: bench/parse-formatting.json

The ignored-end-tag case places 1,000 ``</address>`` tokens beneath 256 open ``span`` elements, with text before and
after the sequence. Default-scope queries reuse their result until the open stack changes. Matched local runs reduced
full-parse time by 68.9%; the ordinary nested-formatting control took 1.1% longer. The case parses ASCII input with
source locations disabled and includes document cleanup. CodSpeed tracks the same input.

.. bench-table::
    :file: bench/parse-scope.json

The formatting-attribute cases nest 256 ``b`` elements with either distinct ``title`` values or one repeated value. An
unseen attribute fingerprint skips the active-formatting duplicate scan; previously seen fingerprints retain the full
comparison and the three-entry limit. Matched local runs reduced full-parse time by 52.5% for distinct values; identical
values took 2.1% longer. Both cases use ASCII input with source locations disabled and include document cleanup.
CodSpeed tracks both. The capacity rules allocate 4 KiB for the distinct case and 256 bytes for the repeated case.
Removed formatting entries leave fingerprints until a scope reset; allocated capacity remains until document teardown.

Turbohtml leads the measured parsers on distinct attributes. Resiliparse takes 29.9 µs on identical attributes, compared
with turbohtml's 49.7 µs. The selectolax identical-attribute result has 10% spread and does not support a precise
comparison. Default lxml and pyquery truncate both inputs to 254 ``b`` elements and discard the text; those cells have
no timing. The html5-parser environment has the libxml2 import mismatch described above.

.. bench-table::
    :file: bench/parse-afe.json

The NUL cases parse 1,000 paragraphs with either one NUL in the first paragraph or clean text throughout. Clean text
runs can retain source spans even when another token contains a NUL. Matched local runs reduced full-parse time by 24.6%
on the early-NUL input; the clean control changed by less than 1%. Both inputs use ASCII, disable source locations, and
include document cleanup. CodSpeed tracks both.

Turbohtml leads the measured parsers on both inputs. On the early-NUL input, BeautifulSoup's ``html.parser`` backend
retains U+0000; its lxml backend, lxml, and pyquery replace it with U+FFFD. Those results differ from turbohtml's NUL
removal and have no timing. The clean-input BeautifulSoup lxml and pyquery measurements have 6% spread and do not
support precise comparisons. The html5-parser environment has the libxml2 import mismatch described above.

.. bench-table::
    :file: bench/parse-nul.json

******************
 Fragment parsing
******************

:func:`turbohtml.parse_fragment` parses an ``innerHTML``-style snippet in a container's context rather than a whole
document, against lxml's ``lxml.html.fromstring`` and html5lib's ``parseFragment``. The input is a table-row fragment
parsed in its ``<tbody>`` context, where the WHATWG algorithm's table rules apply. turbohtml runs the same C engine it
uses for whole documents, so it parses the fragment nearly four times faster than lxml and roughly eighty-eight times
faster than the pure-Python html5lib.

.. bench-table::
    :file: bench/fragment-parsing.json

**********
 Querying
**********

Each library parses the document once, then the timed call runs one query. ``find`` collects every ``<a>`` element the
way each library reaches for it (turbohtml's :meth:`~turbohtml.Node.find_all`, resiliparse's and selectolax's lexbor
selectors, lxml's XPath ``findall``, parsel's and pyquery's and BeautifulSoup's selectors, and soupsieve directly). A
tag-only query resolves the name to an interned atom and walks the subtree comparing integers, with no per-element
string built and no matcher dispatch. It stays ahead of resiliparse's lexbor pass by 1.3 times on the small blog
widening to 22 times on the spec, leads lxml's C XPath engine by 14 to 24 times, and runs 12 to over 1,400 times ahead
of pyquery, selectolax, parsel, BeautifulSoup, and soupsieve.

A first-result query walks until its match when the document has no tag index. An uncapped ``find_all`` builds the
whole-document index for later queries; ``find`` and ``find_all(..., limit=1)`` reuse it after that point. The cold-tree
benchmark records hit positions and misses. It measures uncapped and limited collection, plus peak resident memory.

.. bench-table::
    :file: bench/querying.json

``select`` runs the CSS selector ``div a[href]`` (turbohtml's :meth:`~turbohtml.Node.select`, resiliparse's and
selectolax's ``css``, lxml's `cssselect <https://github.com/scrapy/cssselect>`_, parsel's ``css``, pyquery, and
BeautifulSoup's `soupsieve <https://github.com/facelessuser/soupsieve>`_). turbohtml compiles the selector against the
tree once and matches interned integer atoms. lxml and parsel translate the selector to XPath through cssselect on each
call. These controls complement the positional-selector scaling cases below.

.. bench-table::
    :file: bench/querying-2.json

The relational ``:has()`` pseudo-class can require scanning a candidate's subtree. This comparison runs ``div:has(a)``
against the same pages. turbohtml memoizes subtree searches within the query and skips sibling scans for descendant and
child relationships.

.. bench-table::
    :file: bench/querying-3.json

Per-element matching runs each anchor on the page through a compiled ``div a[href]`` matcher -- the shape a soupsieve
port hits through :mod:`turbohtml.query` and its :meth:`Matcher.match <turbohtml.query.Matcher.match>` -- raced against
selectolax's node match, soupsieve, BeautifulSoup, and pyquery. turbohtml answers each test with the same interned-atom
comparison its ``select`` uses, walking the ancestor chain once per candidate. This control measures individual matching
separately from collecting query results.

.. bench-table::
    :file: bench/matching.json

:func:`turbohtml.query.escape_identifier` escapes a raw string into a CSS identifier per the CSSOM
serialize-an-identifier rules -- the safe way to drop an untrusted class or id into a selector -- against soupsieve's
``escape``. The workload escapes a thousand identifiers spanning leading digits, embedded specials, astral characters,
and a lone dash. turbohtml walks the code points and emits the escape in C, where soupsieve builds the result through a
per-character Python loop, so it runs 16 times faster.

.. bench-table::
    :file: bench/querying-6.json

A text-content search runs through :meth:`~turbohtml.Node.find_all` with ``text=`` (a regex matched against each
element's collected subtree text), raced against ``BeautifulSoup.find_all(string=...)`` and the equivalent text filters
on lxml, parsel, and pyquery. When the ``text=`` filter is a plain string or a literal (no regex metacharacters,
case-sensitive) compiled pattern, turbohtml gathers each candidate's collected text and matches it in C -- no Python
``str`` built, no per-element ``re.search`` call -- where the others walk the tree in Python, so it leads every
competitor by 1.2 to 3.0 times across these pages. A case-insensitive or otherwise non-literal pattern keeps the
per-element Python path.

.. bench-table::
    :file: bench/querying-4.json

:func:`turbohtml.convert.css_specificity` weighs a selector list's ``(a, b, c)`` specificity, raced against `cssselect
<https://github.com/scrapy/cssselect>`_'s ``Selector.specificity()``, the computation lxml, parsel, and pyquery inherit.
turbohtml parses the selector and sums the weights in one C pass, so it leads across the type, compound, structural,
complex, and grouped selectors below; cssselect parses in Python and builds a tree of selector objects first.

.. bench-table::
    :file: bench/css-specificity.json

The XPath table compares :meth:`~turbohtml.Node.xpath` with lxml and parsel on one 9.6 kB web-platform-tests page. Run
``tox -e bench -- --pgo xpath`` to reproduce it. Cases cover axes and predicates, string and aggregate functions,
ordered unions, and computed name tests. turbohtml resolves name tests to interned atoms and can collapse ``//`` to a
single descendant walk. Positional predicates preserve proximity order. Ordered result sets avoid another sort, and
unions merge their sorted inputs.

The remaining cases cover variable bindings, namespaces, EXSLT functions, extension callbacks, and precompiled
expressions. Node-set variables and extension results feed later path steps. The namespace case adds an SVG fragment to
the page. For ``re:test``, turbohtml uses Python's :mod:`re` and lxml uses libexslt. ``set:distinct`` retains the first
node for each string value. Five XPath 2.0 string-function rows have no libxml2 equivalent. The precompiled case reuses
:class:`~turbohtml.XPath` or lxml's ``etree.XPath`` to exclude expression parsing from the timed call.

.. bench-table::
    :file: bench/querying-5.json

******
 XSLT
******

:class:`turbohtml.transform.Transform` compiles one stylesheet into a native model with reusable XPath programs. Each
application allocates source-specific indexes and output state. Callers can use one ``Transform`` instance with
different documents and parameters across threads.

The first table measures construction. The next two measure a 120-row catalog and ten calls to a 300-template
stylesheet. That stylesheet has 299 unused templates and 24 static ``xsl:number`` patterns in its used template; the
repeated result includes any stylesheet analysis or XPath compilation left in the application path.

.. bench-table::
    :file: bench/xslt-compile.json

.. bench-table::
    :file: bench/xslt.json

.. bench-table::
    :file: bench/xslt-reuse.json

The template-rule cases visit 1,024 nodes once or eight times, with 128 unmatched templates before the winning rule.
Caching the winning rule for each node, attribute, and mode reduced elapsed time by 35.94% for eight passes and
increased it by 3.69% for one pass in the matched release-build comparison. Each application frees its cache when it
finishes; the compiled stylesheet retains no source nodes.

.. bench-table::
    :file: bench/xslt-rules.json

The declaration-name cases call a named template 256 times. Each call uses an attribute set and resolves an XSLT key.
With 256 unused declarations of each kind, name indexes reduced application time by 27.13%; the small control improved
by 1.76%. Compilation builds the immutable name indexes once. Applications share them while keeping their own key result
tables. The table measures application after compilation; constructor cost is separate.

.. bench-table::
    :file: bench/xslt-names.json

The same large stylesheet costs 2.29% more to compile (179.21 µs to 183.32 µs). The compilation benchmark uses eight
fixed loops to bound temporary tree allocations. On this 64-bit build, its name-index arrays and attribute-set links
retain 75,784 bytes per compiled stylesheet, excluding allocator overhead. Index fields add 56 bytes to the model and
each call's engine state.

.. bench-table::
    :file: bench/xslt-names-compile.json

The sibling-numbering cases use one or eight default ``xsl:number`` instructions per node. Forward traversal can reuse
the preceding sibling's count; repeated instructions can reuse the current node's count. Reverse sibling traversal still
needs preceding-sibling scans for each newly visited node. The one-node and zero-instruction cases measure fixed
overhead.

The ``any:`` cases number matching nodes across the document. Repeated default ``level="any"`` numbering caches their
counts, including for reverse visits. The first call and repeated calls for the same node allocate no index; subsequent
calls for different nodes retain only matching nodes until the application finishes. Cases with one final-node visit,
alternating names, intervening text/comments, and an explicit ``count`` pattern cover different reuse opportunities.

Explicit ``count`` and ``from`` patterns reuse their match sets within one application when their expressions depend
only on the source tree. This includes unprefixed names, wildcards, the document root, static predicates, and unions.
Instructions with identical pattern text share those sets. Different pattern text replaces the retained set; variables,
namespace-prefixed steps, and extension calls retain per-call evaluation. The pattern cases include single calls,
section resets, reverse visits, repeated instructions, wildcards, and empty match sets. The ``count-current`` row checks
turbohtml compatibility only: XSLT 1.0 `forbids current() in patterns
<https://www.w3.org/TR/xslt-10/#function-current>`_, and lxml gives different results.

Static explicit ``level="any"`` numbering retains prefix counts, including zero counts and ``from`` resets. A single
visit and repeated visits to the same node avoid index allocation; a second distinct visit builds the index. The
last-node-only cases measure that boundary, and alternating names exercise changes to the default count criteria.

The 1,024-node static-predicate case fell from 38.214 to 0.253 ms in matched release runs (99.34% less time). The
dynamic ``current()`` control changed from 195.407 to 193.810 ms. CodSpeed tracks the static-predicate case separately.

.. bench-table::
    :file: bench/xslt-number.json

The instruction-dense stylesheet combines numbering with variable bindings, comments, copied subtrees, and messages.
These tables time application of a compiled stylesheet to a parsed document. turbohtml returns a Python string; lxml
returns its result-tree object, with conversion to a Python string outside timing. The numbering and instruction-dense
measurements use CPython 3.14.7 and a release build without PGO or LTO.

.. bench-table::
    :file: bench/xslt-dense.json

************
 Node paths
************

Use :meth:`turbohtml.Element.css_path` or :meth:`~turbohtml.Element.xpath_path` to generate a locator from the document
root. The comparison uses lxml's ``getroottree().getpath()`` and parsel's wrapper for positional XPath paths. Each timed
call generates paths for the elements in a pre-parsed page. Both turbohtml methods reuse sibling positions across calls;
structural mutations clear those positions. CSS paths use a per-tree ID-occurrence map to choose unique anchors, which
ID edits invalidate. The fresh-tree cases below measure cache setup costs.

.. bench-table::
    :file: bench/node-paths.json

**************
 Text content
**************

The ``text`` suite collects the visible text two ways. First, the raw text join off a pre-parsed tree, the ``get_text``
pass: turbohtml's :attr:`~turbohtml.Node.text` property concatenates every descendant text run, against lxml's
``text_content()``, resiliparse's node text, selectolax's ``text()``, BeautifulSoup's ``get_text()``, and parsel's and
pyquery's text extraction. turbohtml gathers the runs in one C walk into a buffer reserved up front, so it stays level
with lxml and resiliparse, leads selectolax by 6.6 to 9.3 times and BeautifulSoup by 5.5 to 7.5, and runs 99 to 145
times ahead of parsel, which boxes each match in a wrapper first. pyquery trails by 33 to 57 times.

.. bench-table::
    :file: bench/text-content.json

Second, the layout-aware string-to-text extraction: :meth:`turbohtml.Node.to_text` against `inscriptis
<https://github.com/weblyzard/inscriptis>`_, the layout-aware HTML-to-text renderer it succeeds, `html-text
<https://github.com/zytedata/html-text>`_, Zyte's plainer visible-text extractor, and `resiliparse
<https://github.com/chatnoir-eu/chatnoir-resiliparse>`_'s ``extract_plain_text``. inscriptis and html-text both build an
lxml tree in Python and resiliparse renders text off the lexbor tree it parses to, where turbohtml does the whole layout
in one C walk; inscriptis additionally lays tables out as aligned columns, which html-text and resiliparse skip.
turbohtml leads resiliparse by 2.4 to 4.1 times, html-text by 12 to 18 times, and inscriptis by 34 to 47 times.

.. bench-table::
    :file: bench/text-content-2.json

The ``collapsed`` row turns layout guessing off: turbohtml joins the :attr:`~turbohtml.Node.stripped_strings` word
stream against html-text's ``extract_text(guess_layout=False)``, 17 times faster; inscriptis and resiliparse have no
comparable collapsed mode. The ``main`` row strips page boilerplate first, :meth:`~turbohtml.Node.main_text` against
resiliparse's ``extract_plain_text(main_content=True)``, four times faster. The ``annotated`` row labels matching
elements with spans through :meth:`~turbohtml.Node.to_annotated_text` against inscriptis's ``get_annotated_text``, 75
times faster; html-text and resiliparse have no annotation surface, so they sit out that row.

*****************
 Tree navigation
*****************

Walking every descendant of a parsed tree: turbohtml's :attr:`~turbohtml.Node.descendants` iterator against
resiliparse's node walk, BeautifulSoup's ``descendants``, lxml's ``iterdescendants()``, selectolax's node iteration,
pyquery, and html5lib. The ``list(el)``, ``iterdescendants()``, and ``iterancestors()`` family ports to
:attr:`~turbohtml.Node.children`, :attr:`~turbohtml.Node.descendants`, and :attr:`~turbohtml.Node.ancestors`; the
descendant walk is the dominant case. Each timed call consumes the whole iterator, where turbohtml yields interned nodes
straight from the arena faster than lxml's libxml2 proxy objects and BeautifulSoup's Python ``NavigableString`` chain.
resiliparse's lexbor walk stays closest at 1.4 to 2.0 times and BeautifulSoup's ``descendants`` -- one of its leaner
paths -- at about twice, while lxml and selectolax trail by five times, pyquery by twenty, and html5lib by ninety.

.. bench-table::
    :file: bench/tree-navigation.json

*************
 Serializing
*************

Serializing a parsed document back to HTML: turbohtml's :attr:`~turbohtml.Node.html` against resiliparse's, pyquery's,
selectolax's, parsel's, and lxml's serializers, BeautifulSoup's ``decode``, and html5lib. turbohtml scans each text run
for the next character that needs escaping (two code points at a time with the same SWAR lane probes
:func:`~turbohtml.escape` uses) and bulk-copies the clean spans, recovering each special's position from the lane mask,
and reserves the whole-document buffer up front so the output grows in one allocation. It serializes about twice as fast
as resiliparse and pyquery, four to six times faster than selectolax, parsel, and lxml, and 52 to 77 times faster than
BeautifulSoup and html5lib.

.. bench-table::
    :file: bench/serializing.json

***********
 Minifying
***********

Minifying a document with :func:`turbohtml.clean.minify`: parse, then serialize once with every fold engaged (collapsing
insignificant whitespace, omitting the WHATWG-optional tags, unquoting attributes, and stripping comments), against
`minify-html <https://github.com/wilsonzlin/minify-html>`_'s Rust minifier on the same folds (its CSS and JS
minification left off for a like-for-like comparison), the pure-Python `htmlmin <https://github.com/mankyd/htmlmin>`_
and ``css-html-js-minify``, and the native CLI minifiers `html-minifier-terser
<https://github.com/terser/html-minifier-terser>`_ and `tdewolff/minify <https://github.com/tdewolff/minify>`_.
turbohtml parses and emits in C through one preallocated buffer, so with the parse included it runs roughly two to three
times faster than minify-html and sixteen to seventy times faster than the pure-Python pair. html-minifier-terser and
tdewolff are invoked through their command line, so their millisecond timings are dominated by process startup; the
clean comparison against them is output size. turbohtml lands within about two percent of html-minifier-terser on the
structural folds both apply; minify-html folds more aggressively for roughly three to ten percent smaller, and tdewolff
goes further still by also minifying the inline CSS and JavaScript turbohtml leaves untouched here.

.. bench-table::
    :file: bench/minifying.json

**********
 Building
**********

The write path: construct a ``<ul>`` of ``N`` ``<li>`` rows from scratch (each with a ``class``, a ``data`` attribute,
and a text child), then serialize it, the work an editor or template engine does. turbohtml's arena allocation and
interned attribute names make construction cheaper than lxml's libxml2 nodes and far cheaper than BeautifulSoup's Python
objects. selectolax is parse-only, so it has no entry.

.. bench-table::
    :file: bench/building.json

The ``construct`` and ``emit`` commands split that aggregate over the same builders: ``construct`` builds the rows and
stops before serialization, and ``emit`` serializes a tree built once outside the timed region. On construct turbohtml's
arena keeps it roughly twice as fast as lxml and ahead of most Python builders, though the leanest string builders
markyp and simple-html edge it out; on emit its SWAR serializer pulls ahead of every alternative, from 1.6 times over
simple-html to eight times over lxml and ninety times over BeautifulSoup.

.. bench-table::
    :file: bench/building-2.json

.. bench-table::
    :file: bench/building-3.json

The terse :data:`turbohtml.build.E` builder spells the same ``<ul>`` declaratively, raced against ten dedicated HTML
generators. The leanest string builders `simple-html <https://github.com/keithasaurus/simple_html>`_ and `markyp
<https://github.com/volfpeter/markyp-html>`_ build it faster (0.4x and roughly 0.9x), `yattag <https://www.yattag.org>`_
runs on par, and ``E`` leads the rest -- lxml.builder, htbuilder, fast-html, hyperpython, htpy, `dominate
<https://github.com/Knio/dominate>`_, and airium -- by 1.5 to 7 times, and unlike any of them it returns a real,
queryable turbohtml tree rather than a string. That tree costs a little over twice the raw :class:`~turbohtml.Element`
constructor above -- the price of the leading-mapping and per-child dispatch the sugar runs in Python.

.. bench-table::
    :file: bench/building-4.json

*********
 Editing
*********

Editing a parsed tree: tag every ``<a>`` with ``rel="nofollow"``, a link-rewriting pass. Because the pass mutates the
tree, each library rebuilds a fresh parse before every iteration outside the timed region, then the timed call walks its
links and sets the attribute (turbohtml through the live :attr:`~turbohtml.Element.attrs` mapping, resiliparse and
selectolax through their node setters, lxml through ``Element.set``, pyquery through its ``attr``, BeautifulSoup through
item assignment). turbohtml leads resiliparse by 1.4 to 2.1 times, lxml by 1.7 to 3.7, selectolax by 3.0 to 4.9, and
pyquery and BeautifulSoup by 2.8 to 12 times, the gap widening with the page as each reparse costs more.

.. bench-table::
    :file: bench/editing.json

A second pass churns the class list: add then drop a token on every link (turbohtml's
:meth:`~turbohtml.Element.add_class`/:meth:`~turbohtml.Element.remove_class` against resiliparse's, selectolax's, and
pyquery's class edits, lxml's ``classes`` set, and BeautifulSoup's attribute assignment). The add-then-remove is a net
no-op, so each repeat does equal work. turbohtml leads resiliparse by three to six times, selectolax and lxml by roughly
ten to eighteen times, and BeautifulSoup by up to thirty-seven times.

.. bench-table::
    :file: bench/editing-2.json

Two content setters replace the body's children on a freshly parsed tree. :meth:`~turbohtml.Element.set_inner_html`
reparses a fixed fragment in the ``<body>``'s context and splices it in one C call, against lxml clearing the body and
appending ``fragments_fromstring``, pyquery's ``.html()``, and BeautifulSoup clearing it and appending a reparsed soup;
it leads them by 6.6 to 9.4, 1.7 to 11, and 15 to 42 times. :meth:`~turbohtml.Element.set_text` replaces the children
with one verbatim text node, against the same three, leading by 6.8 to 9.9, 2.3 to 14, and 11 to 22 times. BeautifulSoup
trails furthest because it reparses the whole page on every iteration where the others splice into a live tree.

.. bench-table::
    :file: bench/editing-3.json

.. bench-table::
    :file: bench/editing-4.json

A bulk tag edit over each page's ``<code>``/``<a>``/``<q>`` elements: :meth:`~turbohtml.Node.remove` drops each match
with its subtree, and :meth:`~turbohtml.Node.strip_tags` unwraps each match but keeps its content. Both rewrites are
destructive, so the timed call parses the page afresh -- the string-to-result transform these helpers perform -- and
races each library's own bulk tag helper: w3lib's regex ``remove_tags``, resiliparse, lxml, pyquery, selectolax, and
BeautifulSoup. On ``strip_tags`` turbohtml's single C pass leads every alternative by roughly three to seven times, and
BeautifulSoup by nearly sixty. On ``remove`` it leads the tree libraries by the same margin but trails w3lib's
pure-regex strip on the larger pages, where deleting whole subtrees by regex skips the per-node work a real tree edit
does.

.. bench-table::
    :file: bench/editing-5.json

.. bench-table::
    :file: bench/editing-6.json

Use :meth:`~turbohtml.Element.normalize` after edits leave adjacent text nodes. It sizes each run before copying the
merged text, limiting repeated work and arena growth. The first nonempty text node survives; references to removed nodes
remain valid as detached nodes. It removes empty text nodes.

These cases vary the number and length of text nodes, with construction outside the timer. The measurements use CPython
3.14.7 and a release build without PGO or LTO, with CPU-headroom and memory-pressure guards. The one- and two-node
controls include per-call timer overhead. CodSpeed tracks the 1,000-node case, the longer-text case, and a nonempty node
followed by 1,000 empty nodes. Removing those empty nodes during the sizing pass reduced elapsed time from 2.336 to
1.246 µs (46.66%); the 1,000-nonempty-node control showed no regression. We reused its unchanged baseline measurements
for the final control comparison; the table retains the sample-spread warning.

.. bench-table::
    :file: bench/normalize-dom.json

Constructing a :class:`~turbohtml.Range` validates its offset against the container's children. Validation stops once it
reaches the requested offset. These cases construct and discard a collapsed range at offset 0 or 1,000 in an element
with 1,000 children. Each iteration builds a fresh tree outside the timer. CodSpeed tracks both offsets.

On CPython 3.14.7 with a release build without PGO or LTO, the offset-zero comparison fell from 2.083 to 0.676 µs
(67.55% faster). The end-offset control rose from 2.110 to 2.202 µs (4.38% slower). Each measurement times one call and
includes timer overhead; the samples were noisy. CPU-headroom and memory-pressure guards accepted both comparisons.

.. bench-table::
    :file: bench/range-boundary.json

Cloning a range of complete children resolves their interval once, avoiding repeated boundary comparisons for each
child. These cases clone all 1,000 children or a single child, with tree and range construction outside the timer.
CodSpeed tracks both cases. On the same release configuration, the 1,000-child comparison fell from 1,487.138 to 10.498
µs (99.29% faster); the single-child mean fell from 0.359 to 0.331 µs (7.64% faster). The single-child samples have 10%
relative standard deviation and include per-call timer overhead. We ran both comparisons under CPU-headroom and
memory-pressure guards.

.. bench-table::
    :file: bench/range-contained.json

Cloning a partial element copies its tag and attributes without copying descendants outside the range. These cases
select the first three characters of an element's text, excluding 1,000 sibling elements or one sibling. Construction
runs outside the timer; CodSpeed tracks both cases. Under the same release configuration and resource guards, the
1,000-sibling comparison fell from 13.999 to 3.723 µs (73.41% faster). The single-sibling mean fell from 0.441 to 0.374
µs (15.18% faster); those samples include per-call timer overhead and have 12% relative standard deviation.

.. bench-table::
    :file: bench/range-partial.json

:class:`~turbohtml.MutationObserver` checks event options before walking ancestors to determine whether a registration
covers a mutation. These cases register 1,000 unrelated nodes and edit an attribute 100 levels deep. The target requests
child-list events; the control requests attribute events, so it still needs the ancestry checks. Construction and
registration happen outside the timer; timing covers one attribute edit and draining the empty record queue.

Under the same release configuration and resource guards, rejecting the wrong event kind fell from 57.659 to 1.466 µs
(97.46% faster). The same-kind control rose from 57.886 to 59.572 µs (2.91% slower). CodSpeed tracks both cases.

.. bench-table::
    :file: bench/observe-registrations.json

Adding attributes through ``element.attrs`` reserves space for later insertions, reducing array copies and retained
arena buffers on elements with many attributes. Replacement cases exercise existing names; they do not benefit from
extra capacity. The insertion benchmarks construct their input outside the timer.

These attribute tables use CPython 3.14.7 and a release build without PGO or LTO. Memory columns include imports and one
operation in a fresh process, so import-time memory can hide differences on small inputs. The XML cases include parsing
and check attribute-growth costs alongside name and namespace validation. CodSpeed covers 1,000 insertions,
replacements, and XML attributes.

.. bench-table::
    :file: bench/attribute-grow.json

.. bench-table::
    :file: bench/parse-xml-attrs.json

Use :meth:`~turbohtml.Node.equals` to compare subtree contents; ``==`` compares node identity. Attribute order does not
affect equality. For elements with at least 32 attributes, repeated name searches trigger a temporary index after two
comparisons per attribute on average. Early mismatches return before allocating the index.

These cases compare two detached elements with string-valued attributes, varying their count and order, with mismatches
at either end. Tree construction happens outside the timer; both adapters include a cached pair lookup. BeautifulSoup
uses ``Tag.__eq__`` on the same inputs, independent of its parser backend. The measurements use CPython 3.14.7 and a
release build without PGO or LTO. CodSpeed tracks the 1,000-attribute inputs and the duplicate-name control.

The duplicate-name control uses constructor keys that normalize to the same HTML attribute name. It retains the first
matching value when comparing attributes. BeautifulSoup preserves key casing in constructor input, so that row has no
equivalent comparison.

Matched direct-call measurements of 1,000 reversed attributes fell from 1,490 to 30 microseconds after indexing, a 98%
reduction. The table includes the adapter lookup overhead. BeautifulSoup remains faster on the large equal-attribute
cases; its Python dictionary comparison avoids constructing a temporary index.

.. bench-table::
    :file: bench/node-equals.json

*******
 Links
*******

The link surface: extract every in-document link, resolve them against a base URL, and rewrite them through a callback.
turbohtml's :meth:`~turbohtml.Node.links`, :meth:`~turbohtml.Node.resolve_links`, and
:meth:`~turbohtml.Node.rewrite_links` walk the full set of link-bearing attributes (``href``, ``src``, ``srcset``, ...);
lxml.html's ``iterlinks()``, ``make_links_absolute()``, and ``rewrite_links()`` are the only like-for-like set. The
tables also carry the anchor collectors resiliparse, selectolax, BeautifulSoup, parsel, and pyquery, which read only
``<a href>`` and so do strictly less work. Each operation runs over the three real saved pages and the 235 kB WHATWG
spec; extraction is read-only and rewrite applies an identity callback, so both reuse one cached parse, while absolutize
rebuilds a fresh tree before each iteration since ``make_links_absolute`` rewrites the hrefs in place. turbohtml walks
the attribute set in C and leads lxml's like-for-like helpers from seven times up to over a hundred times, the gap
widening with the link count; against the anchor-only collectors it does more work per element, so resiliparse and
selectolax land near or just ahead on extraction while turbohtml pulls away on the rewrite.

.. bench-table::
    :file: bench/links.json

.. bench-table::
    :file: bench/links-2.json

.. bench-table::
    :file: bench/links-3.json

************
 Extraction
************

Pulling values out of a document, the idioms the parsel, pyquery, and w3lib migrations center on. First, reading every
matched node's ``@href`` and visible text off a pre-parsed page: turbohtml selects once and reads
:meth:`~turbohtml.Element.attr` and :attr:`~turbohtml.Node.text` off each node, against resiliparse, lxml, selectolax,
parsel, and pyquery selecting and reading, and BeautifulSoup. turbohtml compiles the selector once and reads interned
atoms, where the others re-translate the CSS per call or box every match in a wrapper object, so it leads resiliparse by
two to six times, lxml and selectolax by five to seventeen times, parsel and pyquery by twenty to seventy times, and
BeautifulSoup by up to 260 times.

.. bench-table::
    :file: bench/extraction.json

.. bench-table::
    :file: bench/extraction-2.json

Second, reading a document's own URL hints: turbohtml's :meth:`~turbohtml.Document.base_url` and
:meth:`~turbohtml.Document.meta_refresh` against w3lib's ``get_base_url`` and ``get_meta_refresh`` and the same read off
lxml, resiliparse, selectolax, parsel, pyquery, and BeautifulSoup trees. Every alternative parses the string each call;
turbohtml runs the WHATWG tree builder and reads the hint off the parsed ``<head>``, leading w3lib's regular-expression
pass by five to six times and the other parsers by four to forty-six times on this small document.

.. bench-table::
    :file: bench/extraction-3.json

*****************
 Fluent chaining
*****************

A pyquery-style fluent chain over a pre-parsed tree: select every ``<a>``, keep the linked ones, take the first, tag it,
and read its ``href`` (turbohtml's :class:`turbohtml.query.Query` against `pyquery <https://github.com/gawel/pyquery>`_,
whose wrapper delegates to lxml). Both wrappers are thin Python over the underlying engine, so the gap is the engine's:
turbohtml's selector and attribute primitives run in C, and the wrapper avoids a redundant de-duplication when the chain
starts from one node, so it runs four to nearly fifty times faster, depending on how much the page exercises the
selector.

.. bench-table::
    :file: bench/fluent-chaining.json

*********************
 html.parser adapter
*********************

:class:`turbohtml.migration.stdlib.HTMLParser` against the standard library's :class:`python:html.parser.HTMLParser` and
lxml's target-parser API, all driven with the same minimal handler so the comparison is the parser and dispatch cost for
the identical callback-driven programming model. The per-tag Python handler call is a floor both Python parsers pay.
Dispatch runs in C: the tokenizer calls the ``handle_*`` methods itself, binding them once per feed rather than building
a token object and walking its fields in Python for every token. Under Callgrind that removes 30.8% of the instructions
the whole workload executes, and nearly half its indirect branches, which is what the interpreter spends on dispatch.
turbohtml runs 7.5 to 11.2 times faster than html.parser and 1.7 to 2.7 times faster than lxml's fully native target
parser, which never crosses into Python per tag.

.. bench-table::
    :file: bench/html-parser-adapter.json

******************
 CSS minification
******************

:func:`turbohtml.clean.minify_css` against the CSS minifiers on PyPI, over the unminified source CSS these frameworks
publish. Each minifier column pairs its output size with the time to produce it; the ratio in each cell is against
turbohtml. Sizes are deterministic byte counts; times are the minimum of repeated runs. `esbuild
<https://esbuild.github.io/>`_ and `tdewolff/minify <https://github.com/tdewolff/minify>`_ are native minifiers invoked
through their command line, so their millisecond timings are dominated by process startup; against them the clean
comparison is output size, where turbohtml stays within a couple percent and comes out smaller on most of the corpus.

.. bench-table::
    :file: bench/css-minification.json

``csscompressor`` (the YUI port) and ``cssmin`` (its BSD descendant) rewrite values to their shortest form the way
turbohtml does, but as pure-Python regex passes they turn quadratic on a large stylesheet and trail the C engine by tens
to over four hundred times, ``cssmin`` and ``css-html-js-minify`` reaching roughly four seconds on the 745 kB
``bulma.css`` where turbohtml takes 9 ms. ``rcssmin`` is a C extension and faster than turbohtml, though it only strips
comments and whitespace, so it leaves a larger result everywhere except the custom-property-heavy ``bulma.css``.
``css-html-js-minify`` is among the slowest of the set. The three pure-Python tools and rcssmin also break value safety:
each rewrites the internal whitespace of a custom-property value, which `CSS Variables 1 §2
<https://www.w3.org/TR/css-variables-1/#defining-variables>`_ keeps as the literal token stream that ``var()`` splices
verbatim and ``getPropertyValue()`` reads back byte-exact, and ``cssmin`` and ``css-html-js-minify`` collapse whitespace
inside strings, so their output can change the cascade where turbohtml's round-trips. That rewrite is also the only
reason ``rcssmin`` and ``cssmin`` end 0.2% to 0.3% ahead on ``bulma.css``, whose declarations are almost entirely custom
properties.

`lightningcss <https://pypi.org/project/lightningcss/>`_, the Rust binding, is a cascade-aware optimizer: it drops
declarations overridden elsewhere in the sheet and rewrites syntax for a browser-target set, so it reaches a smaller
size than turbohtml on most of the corpus (turbohtml comes out ahead on ``normalize.css``). That target-dependent
optimization is the same idea as turbohtml's ``baseline`` option carried further, and it is in scope. Its Rust engine
runs 1.3 to 2.4 times slower than turbohtml across the corpus, its per-target cascade pass the added cost, and it
rejects ``foundation.css`` with a parse error on a media query the WHATWG recovery rules accept, where turbohtml
minifies all six. turbohtml gives the smallest value-safe output at the most compatible baseline and recovers from
malformed input.

*************************
 JavaScript minification
*************************

:func:`turbohtml.clean.minify_js` against the PyPI JavaScript minifiers it replaces -- `rjsmin
<https://opensource.perlig.de/rjsmin/>`_ (a regex substitution), `jsmin <https://github.com/tikitu/jsmin>`_ (Crockford's
character state machine), ``css-html-js-minify`` (another regex pass), and `calmjs.parse
<https://github.com/calmjs/calmjs.parse>`_ (a full ES5 parser with an obfuscating printer) -- and the industry's native
minifiers as the size bar: `terser <https://terser.org/>`_ (the JavaScript ecosystem's reference), `esbuild
<https://esbuild.github.io/>`_, and `tdewolff/minify <https://github.com/tdewolff/minify>`_, each invoked through its
command line. The inputs are real un-minified libraries, a size ladder every tool parses. turbohtml renames every local
binding (function and class declarations included) and runs the structural folds, so it beats calmjs.parse's heavier
global obfuscation on size everywhere while running fifty to a hundred times faster, and its output lands within one
percent of terser, esbuild, and tdewolff -- the best minifiers available. It runs in-process, where each native tool
pays its runtime's process startup per file, so it finishes ahead end to end; only rjsmin is faster, and it, jsmin, and
css-html-js-minify all do so by leaving output half again to twice the size. Each cell pairs a minifier's output size
with the time to produce it; both ratios are against turbohtml.

.. bench-table::
    :file: bench/js-minification.json

********************
 Encoding detection
********************

:func:`turbohtml.detect.detect` against the encoding detectors it replaces: `chardet <https://chardet.readthedocs.io/>`_
(the pure-Python prober ensemble), `charset-normalizer <https://charset-normalizer.readthedocs.io/>`_ (decode-and-score,
what ``requests`` uses), `faust-cchardet <https://github.com/faust-streaming/cChardet>`_ (the maintained C binding of
uchardet; the original cchardet stops compiling at Python 3.11), `resiliparse <https://resiliparse.chatnoir.eu/>`_'s
``detect_encoding``, and BeautifulSoup's ``UnicodeDammit``, benchmarked with the ``chardet`` backend it only sniffs
with. turbohtml resolves certain input -- a byte-order mark, a ``<meta>`` declaration, valid UTF-8, pure ASCII --
structurally before any scoring, which is where the tens-to-nearly-2000x rows on the ASCII and pre-declared pages come
from, and its chardetng frequency scoring keeps declaration-less single-byte text 3.9x-5.4x ahead of chardet.

resiliparse's native scan is quickest on the small and CJK inputs, ahead of turbohtml by 1.1 to 2.3 times where the
structural checks find nothing to short-circuit on; faust-cchardet (uchardet) leads only the Shift_JIS row, 1.6 times.
On everything else turbohtml's structural resolution runs away from the full-table scanners: uchardet spends 188
microseconds on the 4 kB UTF-8 stream turbohtml settles in five, and 30 milliseconds on the 95 kB pre-declared page it
settles in under one. CJK is the case both native detectors keep, since turbohtml decodes each candidate encoding to
score it and a CJK stream leaves several standing.

.. bench-table::
    :file: bench/encoding-detection.json

*****************
 Legacy decoding
*****************

The WHATWG decoders against the CPython codecs they replaced: ``cp932`` for Shift_JIS, ``cp1252``, ``gb18030`` and
``iso2022_jp``. None of those is the spec's decoder -- the tables differ, the error handling differs, and
:doc:`/how-to/encoding` explains why no rename could have reconciled them -- so the table prices the replacement rather
than claiming the codecs were a substitute. Each case wraps prose in tags, the shape of a real page, since a decoder
that walks markup one byte at a time pays for it: ASCII runs are copied out whole, and only ISO-2022-JP, whose escapes
can reinterpret an ASCII byte, has to step through them. The ``gb18030 astral`` row, dense with four-byte sequences, is
the one case where the CPython codec's table lookup edges ahead.

.. bench-table::
    :file: bench/legacy-decoding.json

********************************
 URL cleaning & link extraction
********************************

:func:`turbohtml.extract.clean_url`, :func:`~turbohtml.extract.normalize_url`, and
:func:`~turbohtml.extract.extract_links` against `courlan <https://github.com/adbar/courlan>`_, trafilatura's URL
cleaner, and `w3lib <https://w3lib.readthedocs.io/>`_'s ``safe_url_string``/``canonicalize_url``, Scrapy's URL
utilities. The per-URL pass wins 2.8x-7.5x by scanning each component once in C-backed regexes and percent-encoding only
when a scan finds something to encode, where both competitors re-encode unconditionally through urllib's per-character
quoters. Page-level filtered extraction parses the real WHATWG DOM and cleans each link, and finishes 2.2x-3.8x ahead of
courlan's regex scan, because each distinct href is cleaned once and absolute links skip resolution. Every tree-based
competitor here resolves each href against the base and deduplicates the result, the work
:func:`~turbohtml.extract.extract_links` does, so the row compares the same answer rather than a bare attribute read:
lxml trails by 1.3 to 2.1 times, selectolax by 1.6 to 3.5, parsel and pyquery by 2.2 to 3.8, and BeautifulSoup by 8.7 to
38.0 depending on its tree builder.

.. bench-table::
    :file: bench/url-cleaning.json

.. bench-table::
    :file: bench/link-filtering.json

*******************
 Scaling workloads
*******************

These synthetic inputs expose costs that small pages can hide. Their speedups apply to the named workload and size; the
real-page tables above provide separate controls. The query cases reuse a parsed tree. Extraction cases include parsing.
All operations also have entries in the CodSpeed suite.

Sibling queries
===============

The CSS cases distinguish ordinary ``nth-child`` from a filtered sibling list. XPath covers a descendant selection and a
union of list items and their containers.

.. bench-table::
    :file: bench/select-nth.json

.. bench-table::
    :file: bench/xpath-wide.json

The ``set:distinct`` cases vary both node count and the number of distinct string values. The duplicate-heavy cases
measure membership overhead; the unique cases expose repeated comparisons against earlier nodes.

.. bench-table::
    :file: bench/xpath-distinct.json

The set membership cases compare disjoint node sets for intersection, difference, and overlap detection. A separate
overlap case matches the first node, where scanning can finish before building a membership table.

.. bench-table::
    :file: bench/xpath-set.json

Value comparisons distinguish equality from existential inequality: two sets can contain both equal and unequal pairs.
The numeric cases use disjoint ranges and include a first-pair match as a control. Parsing runs before timing.

The 10-node equality and both scalar-equality turbohtml cells use matched CPython 3.14.7 release builds without PGO or
LTO. Long scalar equality fell from 10.070 to 6.961 µs (30.88% less time); the 32-character control fell from 0.356 to
0.328 µs (7.79% less). All twelve measurement runs passed CPU and memory guards. The 10-node candidate retains its 6.33%
spread warning. Other rows and competitor measurements retain their earlier builds.

.. bench-table::
    :file: bench/xpath-compare.json

.. bench-table::
    :file: bench/xpath-order.json

The translation cases vary map size, repeated characters, and cycling ASCII or Unicode text. Early matches and a map
longer than its input check whether building an index costs more than scanning. A short ASCII case-folding input checks
call overhead. These cases reuse a parsed tree and include XPath evaluation and result conversion in each measurement.

The September 10 translation measurements use CPython 3.14.7 and a plain release build without PGO or LTO. Repeated
characters reuse their previous mapping; varied input builds an index after scanning costs exceed its setup cost. The
short-text case retains a direct scan. Competitor cells with high spread retain the table's noise warning.

.. bench-table::
    :file: bench/xpath-translate.json

The ``str:replace`` cases bind strings on a parsed document. The sparse case replaces eight matches of a 129-character
needle whose repeated prefix otherwise forces repeated comparisons. The short ASCII control includes binding and result
conversion. Reusing the substring search reduced elapsed time by 80.96% for sparse matches and 2.79% for the control in
the matched release-build comparison, without PGO or LTO. The installed lxml and parsel XPath engines reject
``str:replace`` as an unregistered function, so this table has no competitor timings.

.. bench-table::
    :file: bench/xpath-replace.json

The ``str:concat`` cases join about 320,000 characters from either 10,000 short nodes or ten long nodes. Parsing runs
before timing. The short-node case measures buffer growth; the long-node control checks the cost of copying text.

.. bench-table::
    :file: bench/xpath-concat.json

The ``id()`` argument cases contain the same 30,000 ID tokens in either 10,000 short nodes or ten long nodes. Both
return two IDs in document order, removing duplicate references. Geometric buffer growth reduced elapsed time by 18.17%
for the short nodes and increased it by 4.72% for the long nodes in the matched release-build comparison.

.. bench-table::
    :file: bench/xpath-id-nodes.json

Shadow slots
============

The scaling cases read assignments for a named slot after a growing sequence of other slots. Empty hosts, comment-only
hosts, and a child assigned to another slot check the cost of returning no assignments. Setup runs before timing. The
ordinary shadow operation includes constructing the host and flattening its children.

.. bench-table::
    :file: bench/shadow-slot.json

Flattening nested fallback slots reuses one scratch buffer for their assigned or fallback children. These cases place
1,000 sibling slots or one slot inside an outer slot, with fallback text in each. Tree construction happens outside the
timer; timing covers ``assigned_nodes(flatten=True)`` on the outer slot. CodSpeed tracks both cases.

On CPython 3.14.7 with a release build without PGO or LTO, the 1,000-slot comparison fell from 29.504 to 23.858 µs
(19.14% faster). The single-slot means were 0.532 and 0.524 µs (1.52% faster), within sample noise and per-call timer
overhead. We ran both comparisons under CPU-headroom and memory-pressure guards.

.. bench-table::
    :file: bench/shadow-fallback.json

Flattening several named slots builds a temporary assignment index after the first slot lookup. The index preserves
first-slot precedence and light-tree child order, then frees its storage before returning. These cases flatten a host
with 1,000 uniquely named slots and matching light children, or one slot and child. Tree construction happens outside
the timer; timing includes building and freeing the index. CodSpeed tracks both cases.

On CPython 3.14.7 with a release build without PGO or LTO, the 1,000-slot comparison fell from 4,997.827 to 84.605 µs
(98.31% faster). The single-slot means were 0.407 and 0.387 µs, within sample noise; we do not claim a control speedup.
All eight comparison runs passed CPU-headroom and memory-pressure guards.

.. bench-table::
    :file: bench/shadow-assignment.json

.. bench-table::
    :file: bench/shadow.json

Schema patterns
===============

The pattern case grows an XML Schema regex character class and validates its last matching character. The catalog cases
measure ordinary XSD and RELAX NG validation. These operations reuse a compiled schema and include parsing the document
to validate.

.. bench-table::
    :file: bench/validate-pattern.json

.. bench-table::
    :file: bench/validate.json

.. bench-table::
    :file: bench/validate-rng.json

Computed styles
===============

The deep case resolves every element in ancestor order. The ordinary and property-dense stylesheets measure separate
costs of matching rules and copying computed values.

.. bench-table::
    :file: bench/computed-style.json

.. bench-table::
    :file: bench/computed-style-dense.json

.. bench-table::
    :file: bench/computed-style-deep.json

Extraction
==========

Microdata cases distinguish local properties, empty scopes, and references in ascending, descending, and interleaved
document order. The unannotated tree measures the cost of discovering that no metadata exists. Article cases increase
the number of candidate containers.

.. bench-table::
    :file: bench/microdata.json

.. bench-table::
    :file: bench/microdata-wide.json

.. bench-table::
    :file: bench/microdata-empty-scope.json

.. bench-table::
    :file: bench/microdata-itemref.json

.. bench-table::
    :file: bench/structured-empty.json

.. bench-table::
    :file: bench/article-wide.json

Nested article candidates share descendant text. The depth cases measure the cost of scoring these overlapping subtrees,
with parsing outside the timed interval.

.. bench-table::
    :file: bench/article-deep.json

Path caching
============

The wide cases request every list item's path on a reused tree. The cold cases start with a fresh parse outside the
timed interval, then request either every item's path or only the last item's path. Measuring one cold path separates
the cache setup cost from the benefit of reusing positions.

.. bench-table::
    :file: bench/path-wide.json

.. bench-table::
    :file: bench/path-xpath-wide.json

.. bench-table::
    :file: bench/path-cold.json

.. bench-table::
    :file: bench/path-xpath-cold.json

.. bench-table::
    :file: bench/path-one-cold.json

.. bench-table::
    :file: bench/path-xpath-one-cold.json

The class-edit case sets each item's class before requesting its path. Those edits leave ID uniqueness intact, so they
should not rebuild the ID-occurrence map.

.. bench-table::
    :file: bench/path-class-edit.json

Text and attribute ordering
===========================

Long disordered combining-mark runs and elements with many reversed attributes exercise ordering costs. The ordinary
normalization and canonicalization inputs measure the smaller workloads alongside them.

.. bench-table::
    :file: bench/normalize.json

.. bench-table::
    :file: bench/normalize-marks.json

.. bench-table::
    :file: bench/canonicalize.json

.. bench-table::
    :file: bench/canonicalize-attrs.json

Language detection
==================

The long-prose cases repeat the same vocabulary to measure trigram counting as input length grows. The ordinary cases
retain the suite's multilingual inputs.

.. bench-table::
    :file: bench/detect-language.json

.. bench-table::
    :file: bench/detect-language-long.json

**************************
 DOM transformation costs
**************************

These cases use a plain release build without PGO or LTO. Each mutation receives a fresh parse outside the measurement.
The pyperf worker collects cyclic garbage between mutations outside the timer, preventing old parsed trees from
accumulating. Competitor columns compare the operations described below. CPU-headroom and memory-pressure checks passed
during collection; each cell contains at least twelve timing values across at least three worker processes.

.. bench-table::
    :file: bench/collapse-whitespace.json

.. bench-table::
    :file: bench/strip-comments.json

.. bench-table::
    :file: bench/transform-tree.json

.. bench-table::
    :file: bench/serialize-inner.json

The following tables cover indented and minified child serialization, UTF-8 encoding, and full consumption of compact
and indented chunk iterators on the same four pages. Iterator timings discard chunks as they arrive; they exclude I/O
and do not join the output. Encoding includes Unicode serialization and conversion to UTF-8. Minified streaming is not
supported.

.. bench-table::
    :file: bench/serialize-inner-indent.json

.. bench-table::
    :file: bench/serialize-inner-minify.json

.. bench-table::
    :file: bench/encode-inner.json

.. bench-table::
    :file: bench/encode-inner-indent.json

.. bench-table::
    :file: bench/encode-inner-minify.json

.. bench-table::
    :file: bench/iterate-inner.json

.. bench-table::
    :file: bench/iterate-inner-indent.json

Dispatcher cases reuse a tiny tree and a bound pipeline with zero, one, four, or sixteen identity callbacks. They
include the benchmark's cached-pipeline lookup and callback execution, but exclude parsing and binding. These are
absolute composition costs; they do not establish a speedup over calling application functions. CodSpeed tracks each
stage count, the serializer variants, and the existing mutation cases through the shared operation registry.

.. bench-table::
    :file: bench/transform-dispatch.json

Competitor transformation paths
===============================

The lxml, BeautifulSoup, and selectolax whitespace adapters walk text and apply an ASCII-space regular expression,
preserving preformatted, raw-text, and foreign contexts. They are application code built on those libraries, not native
whitespace APIs. BeautifulSoup and selectolax replace text nodes; turbohtml preserves existing Text objects. lxml
removes comments through ``strip_elements(..., with_tail=False)``; BeautifulSoup extracts ``Comment`` objects;
selectolax removes comment nodes. Its adapters reject trees containing templates because traversal does not expose their
contents; error cells have no timing ratio. Its pretty serializer produces diagnostic output, so it has no pretty-HTML
comparison column. The combined operation removes comments before collapsing text. Parsing stays outside mutation
timings. Parser recovery and text-node representations differ on malformed documents; these measurements do not
establish parser or policy equivalence beyond the differential cases.

Compact child output uses BeautifulSoup's ``decode_contents``/``encode_contents``, selectolax's ``inner_html``,
pyquery's ``html``, and an html5lib treewalker with the body wrapper omitted. lxml and parsel require concatenating
child serializations while preserving and escaping direct body text. Pretty-printer indentation and whitespace policies
vary; their columns price each library's own pretty output rather than identical bytes. html5lib streams serializer
tokens, while turbohtml streams bounded chunks. Both iterator benchmarks consume their output without joining it.

html5lib minification folds whitespace and omits optional tags and attribute quotes; the adapter filters comments. Its
preservation rules differ for ``listing``, ``title``, and foreign content, and removing a comment can leave two spaces
across separate tokens. Do not treat its minified output as a replacement for DOM mutation or as a guarantee of the same
policy. The migration guide describes these limits.

The ``Python (validated)`` baseline uses turbohtml Nodes and checks the same root, result, and ``None`` contract as the
native dispatcher. Both implementations retain replacement roots and propagate stage errors. The ``stdlib`` baseline
omits these checks and measures iteration and callback cost with an identity value. Use the validated column to compare
implementations of the dispatch contract; the plain loop shows the cost without that contract.

Whitespace available to later traversal
=======================================

The html5lib workflow serializes a parsed tree through its whitespace filter, reparses it, then serializes the resulting
tree. turbohtml collapses the parsed DOM and serializes it. The final serialization makes the changed tree observable on
both sides. These costs include html5lib's required reparse and exclude the initial parse. They retain the policy
differences described above.

.. bench-table::
    :file: bench/whitespace-roundtrip.json

JavaScript child-output workflows
=================================

parse5 and jsdom expose child serialization. Their Python adapters start a Node process, parse the supplied HTML, and
return the body's children through stdout. The following tables include process startup, parsing, serialization, and
pipe I/O; turbohtml parses and serializes in the Python process. These are integration costs for a Python caller, not
in-process JavaScript engine timings. The string workflow decodes stdout; the byte workflow retains UTF-8 bytes.

.. bench-table::
    :file: bench/parse-inner.json

.. bench-table::
    :file: bench/parse-inner-encode.json

Copying and mutating cleanup stages
===================================

``sanitize_node`` and lxml-html-clean's ``clean_html`` return copies of parsed trees. The policies differ: turbohtml
uses an allowlist and lxml-html-clean uses a blocklist. These timings do not establish security equivalence.
``linkify_node`` and lxml-html-clean's ``autolink`` mutate a fresh tree supplied outside the timer; lxml-html-clean
links URLs but not bare email addresses. The adapter disables its example-domain exclusions so the shared input produces
links rather than timing a no-op. Rebuilding inputs outside the measurement prevents later iterations from timing an
already-linked tree. These operations can be stages in an application's cleanup pipeline.

.. bench-table::
    :file: bench/sanitize-node.json

.. bench-table::
    :file: bench/linkify-node.json
