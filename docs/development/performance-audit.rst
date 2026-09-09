###################
 Performance audit
###################

This audit started from ``6bd00f3d90159537cce3bfe2406dce8a7d4906ec`` on September 8, 2026. The inventory covers 172
runtime source, header, stub, and generated-data files, plus 125 Python tooling files. Vendored dependency sources
remain at their pinned revisions. The accompanying measurement data records the source inventory, build settings,
samples, and CPU headroom used for each comparison. Download the :download:`measurement data <performance-audit.json>`
for the source inventory, worker values, and timestamped CPU-idle samples. The data omits local paths and the machine's
hostname.

I researched compiler optimization and traversal techniques before changing production code. LLVM's `vectorization
documentation <https://llvm.org/docs/Vectorizers.html>`_ describes widening loops and diagnosing missed opportunities.
The tokenizer already implements NEON, SSE2, and SWAR scanning. The repository also already builds PGO/LTO release
wheels and validates them on held-out pages; I made no compiler-flag changes. See the `GCC optimization options
<https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html>`_ for those mechanisms.

The main opportunities were repeated scans and unnecessary ordering work. SQLite's `query-planning documentation
<https://www.sqlite.org/queryplanner.html>`_ illustrates reusing an available order and indexing repeated lookups.
Applying that principle to tree traversal is my inference. The `Microdata property-collection algorithm
<https://html.spec.whatwg.org/multipage/microdata.html#the-properties-of-an-item>`_ constrains the implementation:
preserve tree order, stop at nested item scopes, and handle duplicate references and cycles.

****************
 Audit coverage
****************

.. list-table::
    :header-rows: 1
    :widths: 24 40 36

    - - Area
      - Existing costs and mechanisms
      - Disposition
    - - Tokenizer and tree builder
      - SIMD/SWAR scanning, arena allocation, interned atoms, lazy source spans, streaming input
      - Retained these mechanisms; no speculative scanning rewrite
    - - DOM ownership and mutation
      - Shared tree handles, structural cache invalidation, attribute mutation, ranges and shadow trees
      - Added cache version checks and tested mutation boundaries
    - - CSS selection
      - Recounted preceding or following siblings for each positional match
      - Reused positions within a query, with scope, type, and filtered-selector checks
    - - XPath and XSLT
      - Repeated sorting and tree-order comparisons; existing compiled expressions and stylesheet indexes
      - Checked existing order, accelerated adjacent comparisons, and merged sorted unions
    - - Computed styles
      - Repeated ancestor cascade evaluation; stylesheet parsing already cached
      - Kept two computed maps to reuse parent values without sharing mutable result storage
    - - Node paths
      - Recounted same-type siblings; ID uniqueness already indexed
      - Cached requested positions and invalidated stale ID anchors
    - - Microdata
      - Linear visited membership and tree-order sorting; local traversal needs neither
      - Removed local bookkeeping, hashed reference membership, and reused ascending or descending order
    - - Combined metadata
      - Snapshot plus separate JSON-LD, Microdata, OpenGraph, RDFa, and Dublin Core extraction
      - Preserved the snapshot and skipped absent formats; RDFa already had an absence check
    - - Article, links, tables, feeds and dates
      - Candidate lookup, subtree statistics, existing C extraction and specialized parsers
      - Indexed article candidates while preserving insertion order for score ties
    - - Unicode and canonicalization
      - Quick checks and table lookup; insertion sorting is quadratic on long disordered inputs
      - Used stable counting for long combining runs and comparison sorting for large attribute lists
    - - Encoding and language detection
      - ASCII decoder runs and table-driven decoding; sorting all observed trigrams before counting
      - Counted unique trigrams before ranking; retained script detection and model tie rules
    - - Sanitizing, linkifying, URLs and IDNA
      - C tree walks, compiled recognizers, Unicode copies, and PSL/IDNA lookup tables
      - Retained behavior; buffer borrowing needs call-site lifetime and representation evidence
    - - CSS/JS minification and serialization
      - Parsed representations, lookup tables, shared output buffers and streaming emission
      - Retained existing algorithms outside canonical attribute ordering
    - - Validation
      - Compiled XSD/RELAX NG models, regex matching, typed-value comparison and schema indexes
      - Retained compiled models; XPath changes receive indirect XSLT coverage
    - - Python API, adapters and tooling
      - Boundary conversions, benchmark wrappers, generators, build, release and documentation tools
      - Extended the shared benchmark registry, CodSpeed cases, and generated performance tables

****************************
 Implementation constraints
****************************

The pointer maps add storage proportional to the number of visited nodes, candidates, or requested positions. The
language table allocates records for distinct trigrams. Computed-style caching holds two owned property maps, and each
returned result owns its values.

Query position caches last for one query. Path caches last for the tree handle and clear on structural changes. Backward
selector matching and changes of scope can still require sibling scans; the positional scaling results describe forward
query traversal. Computed styles also invalidate after attribute edits. CSS path ID anchors must invalidate after ID
edits because a stale map can miss a new ID and hang during lookup. Public tests cover replacement, collisions, removal,
and a duplicate ID becoming unique.

I retained the structured-data snapshot because Python value constructors can call back into application code during
extraction. Ordered XPath unions normalize both operands because extension functions can return reversed lists and
duplicate nodes. Canonical combining-mark sorting remains stable for equal combining classes.

********************
 Measurement method
********************

All before/after comparisons use the existing ``bench.worker`` and the current shared workload registry. The original
local-Microdata experiment alternated original and optimized source twice. The continuation compares an isolated wheel
at ``4e94072d`` with the working implementation, using matching CPython 3.14.7 and plain release settings: coverage off,
PGO off, and LTO off. The extension builds use Apple Clang 21.0.0; CPython's own compiler metadata reports Clang 22.1.3.
The published performance tables use a separate PGO/LTO build; their numbers are not interchangeable with the
plain-release audit comparisons.

The September 8 release-table refresh covers 34 operations, producing 33 performance tables and refreshing 142 rows
across 15 migration tables. Unmeasured migration rows retain their earlier values. The publication runs use nice ``-10``
with three workers, five values, and two warmups. I accepted a run only with at least two interval samples, mean CPU
idle of at least 20%, and at most 10% of samples below 5% idle. I discarded overloaded runs and retried them; the
download includes accepted and rejected CPU windows. Cells with more than 5% spread retain their noise warnings and are
not a basis for precise comparisons.

Each comparison uses isolated pyperf workers, warmups, and repeated values. I logged CPU idle throughout the timed
windows and excluded saturated runs from performance claims. No audit test suite, compilation, or other benchmark ran
alongside timed workers. Other applications continued to run. Later comparisons use nice ``-10`` for both builds and
their workers; priority does not eliminate timing variation. The data retains the measured spread rather than
interpreting small changes as improvements. See `pyperf's measurement options
<https://pyperf.readthedocs.io/en/latest/cli.html>`_ and `system guidance
<https://pyperf.readthedocs.io/en/latest/system.html>`_.

The added cases distinguish wide and deep trees, ordered and interleaved references, cached and fresh-tree paths,
combining-mark run length, attribute count, and text length. Fresh-tree path setup remains outside the timed interval.
Ordinary page and text cases provide separate controls for setup overhead and small-input regressions.

******************
 Measured changes
******************

The table shows representative scaling cases from the plain-release comparisons. The ratio is the baseline mean divided
by the optimized mean. It describes that workload and input size, not a library-wide speedup. The raw data includes the
smaller sizes, variability, and CPU-idle samples.

.. list-table::
    :header-rows: 1
    :widths: 40 15 15 15 15

    - - Workload
      - Input
      - Before
      - After
      - Ratio
    - - Local Microdata properties
      - 10,000 properties
      - 934 ms
      - 2.50 ms
      - 373x
    - - CSS positional selection
      - 10,000 siblings
      - 94.83 ms
      - 0.166 ms
      - 571x
    - - Filtered CSS positional selection
      - 10,000 siblings
      - 274.7 ms
      - 0.245 ms
      - 1,121x
    - - Computed styles
      - Depth 500
      - 164.39 ms
      - 3.625 ms
      - 45.4x
    - - CSS paths for all elements
      - 10,000 siblings
      - 89.75 ms
      - 1.342 ms
      - 66.9x
    - - XPath paths for all elements
      - 10,000 siblings
      - 91.84 ms
      - 1.306 ms
      - 70.3x
    - - Disordered combining marks
      - 10,000 marks
      - 259.70 ms
      - 0.671 ms
      - 387x
    - - Canonical attribute ordering
      - 10,000 attributes
      - 290.89 ms
      - 1.184 ms
      - 246x
    - - Language detection
      - 1 MiB
      - 39.44 ms
      - 6.856 ms
      - 5.75x
    - - Article candidate scoring
      - 10,000 candidates
      - 20.46 ms
      - 7.831 ms
      - 2.61x
    - - Absent structured metadata
      - 10,000 elements
      - 1.375 ms
      - 1.200 ms
      - 1.15x
    - - Reversed Microdata references
      - 1,000 references
      - 0.900 ms
      - 0.522 ms
      - 1.72x
    - - Interleaved Microdata references
      - 1,000 references
      - 3.340 ms
      - 2.718 ms
      - 1.23x
    - - XSLT numeric sort
      - 2,000 rows
      - 1.489 ms
      - 0.383 ms
      - 3.89x

The local-Microdata reversal returned to 990 ms after restoring the original code and to 3.22 ms after restoring the
optimization. Both optimized runs remove the quadratic work. The continuation also improves reference-bearing items; the
first Microdata-only experiment had left an 11% reference-case slowdown unresolved.

The XPath scaling comparison measured ``//li`` over 10,000 siblings at 118.9 ms before and 0.185 ms after. An ordered
union fell from 3.534 s to 0.254 ms. That baseline window had two brief idle samples below 5%, with 44.6% mean idle; the
optimized window had at least 45.1% idle. These figures demonstrate the scaling problem, but the brief baseline
contention limits the precision of the ratios. They do not establish a 642x or 13,921x gain for ordinary XPath queries.

**********************************
 Controls and rejected approaches
**********************************

The initial path implementation indexed every sibling on a cache miss. I removed that approach because one requested
path would pay to index an entire sibling list. The retained cache fills on demand and can reuse the preceding sibling's
position. Separate fresh-tree, single-path, and class-edit cases exercise those costs. A single requested path has no
demonstrated speedup; the optimization targets repeated path generation.

The 100-candidate article case measured 63.96 us before and 65.10 us after; pyperf found no significant difference. The
1,000-candidate case improved from 0.742 ms to 0.607 ms. Ordinary article controls varied across reversed build order,
including slower optimized samples, so the scaling gain does not imply a small-page gain. I did not add a second
candidate lookup algorithm on that evidence.

I retained the existing SIMD scanners, PGO/LTO settings, compiled schemas and expressions, and output-buffer mechanisms.
The audit did not establish an improvement from replacing them. I also retained the structured-data snapshot because
removing it changes callback-visible consistency. None of those proposed rewrites appears in this PR.

Several early runs overlapped heavy external CPU load. Their timings do not support the reported improvements. The
measurement data keeps those control series distinguishable from the selected scaling comparisons. Higher priority
applies to both compared builds, and the load logs remain necessary after changing priority.

************************************
 Correctness and benchmark coverage
************************************

The first pass passed 65,224 tests with 157 skips on Python 3.14. The second pass passed 65,269 tests with 170 skips on
Python 3.13, with 100% Python coverage and 100% coverage of 34,260 C branches under the project's existing exclusion
policy. The PGO/LTO build passed 333 targeted XPath, schema, and shadow-tree tests.

The final diff-coverage check covers 683 executable lines against the original PR base, with no missing lines. Type
checking and the full-PR pre-commit checks pass. The documentation build checks doctests and HTML with warnings as
errors.

Public-API cases exercise XPath extension ordering and distinct values, selector backtracking, computed-style result
ownership, path invalidation, and Microdata tree order. Text cases check stable combining classes and canonical
attribute ordering. The second pass adds growing regex classes and shadow-slot mutation cases.

The selected normalization, canonicalization, CSSOM, XPath and XSLT conformance suites produced the same results on both
builds: 479 passed, 2,340 skipped, 119 expected failures and 49 unexpected passes. Those exclusions reflect the existing
conformance configuration and supported feature set; they do not establish complete standards conformance.

The local CodSpeed suite passed all 163 cases. This PR adds 29 cases across 20 workload families through the existing
registry, including cold paths, interleaved references, and distinct-value cardinality. The final local run used short
wall-time rounds under Python coverage to validate the benchmark call paths. The gated pyperf comparisons supply the
performance evidence; CI supplies CodSpeed's instruction-count comparisons.

The shared workload registry imports turbohtml in its node-input loaders, so isolated competitor environments can load
the registry without installing turbohtml.

Changing an ID after generating a CSS path could leave lookup probing a stale ID map forever. A bounded baseline
reproduction exceeded two seconds; the optimized build returned the old path before the edit and the new path after it.
ID edits now invalidate ID anchors, while unrelated attribute edits keep that map. Computed styles invalidate for either
kind of attribute edit.

**************
 Second audit
**************

The second pass starts from ``cd429483921f8f65adc1fb303662b3671384c107`` and revisits the runtime inventory above. I
checked allocation growth and nested scans in the tokenizer, DOM and shadow trees, XPath set functions, schema
validation, extraction, URL processing, and CSS/JS minification. The first-pass measurements above describe their
original source revisions.

Three candidates remove repeated work. EXSLT ``set:distinct`` rebuilt earlier node string values for each candidate. A
Python set can retain membership while preserving the first node for each value, as required by the `EXSLT specification
<https://exslt.github.io/set/functions/distinct/index.html>`_. The implementation uses the `Python set C API
<https://docs.python.org/3/c-api/set.html>`_ and owns one string per distinct value until the call returns.
Duplicate-heavy inputs measure the cost of that storage and hashing.

The regex parser allocated a replacement range array for each character-class entry. Its arena retained the previous
arrays until validation ended. Geometric capacity growth bounds the accumulated allocations and copies. This changes
character-class construction; the regex matching algorithm remains the same. Russ Cox describes these compilation and
execution stages in his `regular-expression implementation <https://swtch.com/~rsc/regexp/regexp1.html>`_.

Shadow-slot collection searched the shadow tree once per light-tree child. The `DOM slot-assignment algorithms
<https://dom.spec.whatwg.org/#find-slotables>`_ permit finding the first matching slot once, then comparing child slot
names. The implementation defers that search until a light child has the matching name and keeps the result within that
call. Renaming a slot or changing a child's slot attribute requires no persistent cache invalidation. Public tests check
duplicate slot names, assignment order, and mutation in open and closed shadow roots.

I retained the tokenizer's SIMD scanning, JavaScript binding maps, table-grid capacity growth, and indexed schema-name
lookup. Markdown reference creation appends entries without a duplicate scan. Article traversal and URL buffer ownership
need further workload and lifetime evidence before another change; this pass establishes no gain for a rewrite. XPath
intersection and difference still use nested membership checks. The distinct-value optimization does not establish a
gain for those operations.

The new ``xpath-distinct``, ``validate-pattern``, and ``shadow-slot`` workloads extend the shared benchmark registry.
XPath cases vary node count and value cardinality. The ordinary ``xpath``, ``validate``, ``validate-rng``, and
``shadow`` operations provide controls. Nine added CodSpeed entries cover the three workloads, including separate
duplicate-heavy and unique-value XPath inputs, empty results, and nonmatching slot assignments.

I retained the three optimizations after comparing matched plain-release runs. Values below are means with relative
standard deviations; the ratios are approximate. Download the :download:`second-pass measurements
<performance-audit-second.json>` for worker samples, CPU headroom, and superseded candidate versions.

.. list-table::
    :header-rows: 1
    :widths: 40 22 22 16

    - - Workload
      - Before
      - After
      - Ratio
    - - XPath, 1,000 distinct values
      - 18.13 ms ±2.8%
      - 80.91 us ±5.3%
      - 224x
    - - XPath, 10,000 distinct values
      - 1.850 s ±10.6%
      - 0.927 ms ±8.0%
      - 2,000x
    - - XPath, 10,000 nodes with one value
      - 781.4 us ±4.5%
      - 623.5 us ±3.4%
      - 1.25x
    - - Regex class, 32 entries
      - 2.830 us ±4.2%
      - 1.184 us ±4.8%
      - 2.39x
    - - Regex class, 2,048 entries
      - 2.459 ms ±23.9%
      - 13.19 us ±18.3%
      - 186x
    - - 1,000 children, 1,000 preceding slots
      - 1.633 ms ±4.2%
      - 15.74 us ±1.4%
      - 104x
    - - 10,000 children, 10,000 preceding slots
      - 200.9 ms ±15.3%
      - 277.2 us ±13.7%
      - 725x

The controls exposed two regressions during implementation. The first hash-set version allocated a set for an empty
result and made the ordinary ``set:distinct`` control about 12% slower. Empty and singleton inputs now skip string
conversion and hashing. The accepted final control measured 724 ns against a 754 ns baseline. The singleton scaling case
measured 271 ns against 322 ns.

The first slot implementation searched the shadow tree before inspecting light children. With 10,000 preceding slots and
no light children, it took 20.27 us against a 0.083 us baseline. I discarded that form. The retained implementation
skips the search for empty hosts, comments, and children with another slot name. At that size, two accepted empty-host
runs measured 0.115 us and 0.071 us against a 0.080 us baseline; the higher mean had 34% spread. The comment case
measured 16.52 us and 15.37 us against 15.71 us. A nonmatching-child repeat also had high spread, so these controls do
not establish a precise small-input gain.

The final XSD catalog control measured 1.285 ms before and 1.330 ms after, with 2.3% and 12.3% spread. pyperf found no
significant difference for either ordinary XSD case. I make no general XPath speedup claim from the ordinary controls,
which varied across operations whose implementations did not change.

The ordinary shadow operation includes constructing the host and flattening it. Two short final runs measured its
10,000-row case 10% and 21% slower. I repeated both builds with six workers, ten values, three warmups, and a 0.1-second
minimum sample time. That comparison measured 7.73 ms before and 7.02 ms after, with 42% and 15% spread; pyperf found no
significant difference for either the 1,000- or 10,000-row case. The 100-row case measured 73.9 us before and 77.4 us
after, a 5% slowdown. The slot-assignment gains above do not imply faster host construction and flattening.

The second publication refresh covers seven operations, including the ordinary XPath table from the first pass. It adds
six performance tables and refreshes 68 rows across the lxml and parsel migration tables. Together, both passes refresh
39 performance tables and measured rows in 15 migration tables. The generation check compares the committed tables with
accepted feeds and verifies that unmeasured migration rows retain their values.
