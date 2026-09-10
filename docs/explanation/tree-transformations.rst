####################################
 Tree cleanup and output formatting
####################################

For consumers that need normalized node text, collapse whitespace before traversal. Minifying during serialization
leaves the DOM text unchanged, so callers otherwise need to serialize and parse the result before reading normalized
fragments. Native whitespace mutation removes that round trip. Output formatting remains a separate choice: optional
tags and attribute quotes belong to HTML syntax, not to the tree.

************************
 Ownership and ordering
************************

``transform_node`` threads one root through ordinary synchronous callables. Returning a node chooses the next root;
returning ``None`` retains it. This supports existing mutators and copying operations without a transformer base class
or registration. The dispatcher calls each step once, with the root, rather than calling it for each descendant.

Ownership follows the chosen operations. ``sanitize_node`` returns a copy, while whitespace collapse, comment removal,
and linkification mutate the current tree. Retaining the final return value handles both choices. No implicit copy
protects earlier state, and exceptions do not undo earlier mutations. Each native operation locks its tree, but the
composition holds no lock across user callbacks; applications must coordinate a shared sequence that needs isolation.

Order affects results. A comment interrupts a whitespace run, so stripping comments before collapsing can combine runs
that collapsing first would keep separate. A custom step after sanitization can also introduce content outside the
sanitizer's policy. Composition makes the order explicit and leaves that policy decision with the caller.

***********************************
 Whitespace is a contextual policy
***********************************

The native collapse operation applies an HTML text policy, not a CSS layout calculation. It preserves preformatted and
raw-text contexts, including ancestors outside a selected subtree, and skips foreign subtrees. It retains one space at
run boundaries and preserves non-ASCII spaces. It visits template content without entering attached shadow trees. These
limits keep subtree calls consistent with calls on their surrounding HTML tree. XML-mode trees reject collapse because
XML applications can assign significance to any whitespace.

Native traversal avoids creating a Python wrapper for each visited node. Unchanged text keeps its source storage;
changed text needs a replacement buffer, and observers may also need the old text. Tree arenas retain allocations until
you release the tree, so cleanup is not a way to shrink the resident memory of a long-lived tree. The
:doc:`/development/performance` tables exclude parsing from mutation timings and distinguish dispatcher cost from the
work inside its stages.

******************************
 Child output retains context
******************************

Serializing a selected element already limits output to its subtree. ``inner=True`` also omits that element's wrapper.
Keeping the root as serialization context matters for raw text and preserved whitespace; concatenating independent child
serializations can lose that context. A text or comment root has no children and produces empty inner output.

Choose ``inner_xml`` for well-formed XML fragments. Choose ``serialize``, ``encode``, or ``serialize_iter`` with
``inner=True`` for configurable child output. Streaming supports compact and indented HTML; minification requires
``serialize`` or ``encode``. See :doc:`/how-to/transforming-trees` for recipes and :doc:`/reference/clean` and
:doc:`/reference/serialize` for the API contracts.

*********************************
 Alternatives in other libraries
*********************************

Use the operation's ownership and output contract to choose a migration path. A serializer filter changes emitted text;
an in-place transformation changes what later queries and traversals read. Rebuilding a tree from filtered output also
replaces node identity and observer relationships. That distinction matters even when the serialized text agrees.

.. list-table:: Existing library paths
    :header-rows: 1

    - - Library
      - Whitespace and comments
      - Child output
    - - lxml
      - Text/tail adapter; native comment stripping with tails retained
      - Concatenate escaped leading text and child serializations; own pretty-print policy
    - - BeautifulSoup
      - Text-node replacement and comment extraction; same APIs with either parser backend
      - ``decode_contents`` and ``encode_contents``, with optional indentation
    - - selectolax
      - Text replacement and comment removal; template contents are not exposed
      - ``inner_html``; encode the string for bytes. Pretty output is diagnostic, not equivalent HTML
    - - html5lib
      - Whitespace token filter; serialize/reparse when a later tree traversal needs the result
      - Serializer over child tokens, including streaming and optional-tag/quote filters
    - - pyquery / parsel
      - Access to the underlying lxml tree; use its mutation APIs
      - pyquery ``html`` or parsel child selection plus escaped text concatenation
    - - parse5 / jsdom
      - Tree adapters or DOM traversal for application-specific cleanup
      - parse5 ``serialize(node)`` or jsdom ``element.innerHTML``

No shared transformer registration scheme is needed to compose Python operations. A plain callable loop is the baseline;
turbohtml validates roots and stage results and handles replacement ownership. The :doc:`/development/performance` guide
includes the measured adapters and their policy differences.

The `html5lib whitespace filter <https://html5lib.readthedocs.io/en/latest/_modules/html5lib/filters/whitespace.html>`_
preserves a different set of contexts from turbohtml. `BeautifulSoup's output APIs
<https://www.crummy.com/software/BeautifulSoup/bs4/doc/#output>`_ and `selectolax's child serializers
<https://selectolax.readthedocs.io/en/latest/lexbor.html>`_ provide direct child output. `parse5.serialize
<https://parse5.js.org/functions/parse5.serialize.html>`_ serializes children by default.
