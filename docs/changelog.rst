###########
 Changelog
###########

.. towncrier-draft-entries:: Unreleased

.. towncrier release notes start

*********************
 v1.2.0 (2026-07-09)
*********************

Backward incompatible changes - 1.2.0
=====================================

- :func:`turbohtml.detect.detect` reports ``windows-1252``, not ``ascii``, for pure-ASCII input;
  :class:`~turbohtml.detect.EncodingMatch` gained a trailing ``codec`` field; and :class:`~turbohtml.IncrementalParser`
  takes WHATWG labels, so ``latin-1`` raises where ``iso-8859-1`` works. (:issue:`622`)

Features - 1.2.0
================

- Add :attr:`EncodingMatch.codec <turbohtml.detect.EncodingMatch>`; ``data.decode(match.codec)`` reproduces what
  :func:`turbohtml.parse` saw, where ``match.encoding`` corrupted or raised. (:issue:`622`)

Bug fixes - 1.2.0
=================

- Lock free-threaded DOM tree reads and attribute views; concurrent mutation no longer crashes those readers.
  (:issue:`617`)
- Resolve local ``file://`` stylesheet URLs for ``xsl:import``; ``Path.as_uri()`` bases now load sibling imports.
  (:issue:`618`)
- Normalize configured ``Linkify.skip_tags`` names before matching parsed HTML tags; ``CODE`` now skips ``<code>`` text.
  (:issue:`619`)
- Keep controls inside the first ``<legend>`` child of a disabled ``<fieldset>`` in ``form_data()`` output.
  (:issue:`621`)
- Decode legacy bytes with the WHATWG decoders rather than CPython's same-named codecs, whose tables and error handling
  both differ: ``koi8-u`` is KOI8-RU, and GBK ``0x80`` is the euro sign. The ``<meta>`` prescan, the content detector,
  and :class:`~turbohtml.IncrementalParser` now follow the spec too. (:issue:`622`)

*********************
 v1.1.1 (2026-07-08)
*********************

No significant changes.

*********************
 v1.1.0 (2026-07-08)
*********************

Features - 1.1.0
================

- :class:`~turbohtml.clean.Policy` gained ``strip_template_markers``: with it on, sanitizing collapses template-engine
  expressions (``{{ }}``, ``${ }``, ``<% %>``) in kept text and attribute values to a single space, so the output cannot
  re-inject when a template engine renders it. This matches DOMPurify's ``SAFE_FOR_TEMPLATES``. (:issue:`527`)
- :func:`turbohtml.clean.sanitize_report` (and :meth:`turbohtml.clean.Sanitizer.sanitize_report`) sanitize a fragment
  and return what the policy dropped alongside the cleaned HTML: one :class:`turbohtml.clean.Removed` record per removed
  element or stripped attribute, in walk order. This matches DOMPurify's ``DOMPurify.removed``. (:issue:`528`)
- :func:`turbohtml.convert.css_specificity` returns the ``(a, b, c)`` specificity of each selector in a comma-separated
  list, per CSS Selectors Level 4 §17, the value ``cssselect`` exposes as ``Selector.specificity()``. It weighs the
  parsed selector in one C pass, with ``:is()``/``:not()``/``:has()`` taking their most specific argument and
  ``:where()`` contributing zero. (:issue:`529`)
- :func:`turbohtml.extract.feed` normalizes an RSS 2.0, Atom 1.0, or RDF/RSS-1.0 document into one frozen, typed
  :class:`~turbohtml.extract.Feed` of :class:`~turbohtml.extract.Entry` records, the ``feedparser.parse`` entry point
  over :meth:`turbohtml.Document.feed`. It detects the format from the root element and maps each dialect's spelling of
  a field -- the entry ``title``, ``link``, ``id``, ``updated``/``published``, ``summary``/``content``, and ``author``
  -- onto one shape in a single C walk of the parsed tree, over 12x faster than feedparser on a 30-item feed.
  (:issue:`530`)
- :class:`turbohtml.clean.Policy` gains ``transform_tags``: a map that renames elements while sanitizing,
  sanitize-html's ``transformTags``. Map a source tag to a string to rename it, or to a
  :class:`turbohtml.clean.Transform` to rename it and add attributes (sanitize-html's ``simpleTransform``). The rename
  runs before the allowlist in the same C walk, so the renamed element is re-checked from scratch -- a transform decides
  an element's name but never its safety: mapping a tag to ``script`` still drops it, and an added attribute is scrubbed
  like the element's own. (:issue:`531`)
- A new :mod:`turbohtml.saxparse` module adds a DOM-less, event-driven parse. :func:`turbohtml.saxparse.sax_parse`
  drives a document through the WHATWG tree builder and fires a callback on a :class:`turbohtml.saxparse.SaxHandler`
  subclass for each construct it builds -- a start tag, an end tag, a run of text, a comment, the doctype, and a
  ``<?...>`` processing instruction -- while :func:`turbohtml.saxparse.iter_events` yields the same stream as typed
  records. The events reflect the fully spec-correct tree (implied ``html``/``head``/``body``, foster parenting, the
  adoption agency), so unlike :class:`html.parser.HTMLParser` you see the tree the parser built; no per-node Python
  object is created and nothing is retained after the parse, so a one-pass extraction never builds a document-sized
  object graph. The tokenization, tree construction, and walk all run in C. (:issue:`532`)
- ``turbohtml.clean.Policy`` gains ``allowed_styles``, a per-element, per-property value allowlist for the ``style``
  attribute keyed ``{tag: {property: [pattern, ...]}}`` with ``"*"`` matching every tag. A declaration survives only
  when its value matches one of the property's patterns, porting sanitize-html's ``allowedStyles``. It narrows
  ``css_properties`` by value and never weakens the baseline that drops ``expression()`` and disallowed-scheme
  ``url()``. (:issue:`533`)
- :class:`~turbohtml.clean.Policy` gained ``isolate_named_props``: with it on, sanitizing prefixes every kept ``id`` and
  ``name`` value with ``user-content-``, moving it out of the property namespace so it cannot shadow a built-in
  ``document`` or form property through named access (DOM clobbering, where ``<input name="attributes">`` makes
  ``form.attributes`` resolve to the input and ``<img name="body">`` hides ``document.body``). An already-prefixed value
  is left alone, so re-sanitizing is a fixpoint. This matches DOMPurify's ``SANITIZE_NAMED_PROPS``. (:issue:`534`)
- :class:`~turbohtml.Html` gained ``xml``: with ``xml=True``, :meth:`~turbohtml.Node.serialize`,
  :meth:`~turbohtml.Node.encode`, and :meth:`~turbohtml.Node.serialize_iter` emit XML/XHTML instead of HTML -- the
  equivalent of lxml's ``tostring(method="xml")``. Every empty element self-closes (``<br/>``), foreign SVG and MathML
  subtrees carry their namespace declarations, and text and attribute values follow the XML escaping rules, with no HTML
  void-element or raw-text special casing. It composes with ``sort_attributes`` and an :class:`~turbohtml.Indent`
  layout. (:issue:`535`)
- :class:`~turbohtml.clean.Policy` gained a predicate-based custom-element allowance and split content profiles, porting
  DOMPurify's ``CUSTOM_ELEMENT_HANDLING`` and ``USE_PROFILES``. ``custom_element_check`` keeps an unlisted hyphenated
  custom element (``my-widget``, ``x-card``) when a caller-supplied matcher admits its name, ``custom_attribute_check``
  extends the same idea to that element's attributes, and ``allow_customized_builtins`` keeps an ``is`` attribute whose
  value names a custom element. ``allow_html``, ``allow_svg``, and ``allow_mathml`` gate each namespace independently,
  so a policy can keep SVG but drop MathML, or the reverse. All of it runs in the one C sanitize walk, and the
  non-configurable safety baseline -- ``on*`` handlers, ``javascript:`` URLs, unsafe tags -- still applies to whatever a
  matcher keeps. (:issue:`536`)
- :mod:`turbohtml.transform` adds a full XSLT 1.0 processor, the job `lxml <https://lxml.de>`_'s ``etree.XSLT`` does.
  :class:`turbohtml.transform.Transform` compiles a stylesheet (parsed with :func:`turbohtml.parse_xml`) and applies it
  to source documents, and :func:`turbohtml.transform.transform` does both in one call. The whole transform runs in the
  C extension, reusing turbohtml's XPath 1.0 engine for every match pattern and select expression. It covers the entire
  XSLT 1.0 instruction set: templates with ``match``/``name``/``mode``/``priority``, ``apply-templates`` with ``sort``
  and ``with-param``, ``call-template``, ``for-each``, ``if``, ``choose``, ``value-of``, ``copy``/``copy-of``,
  ``element``/ ``attribute``/``text``, ``variable``/``param``, multi-level ``number``, ``key`` with the ``key()``
  function, ``strip-space``/``preserve-space``, ``attribute-set`` with ``use-attribute-sets``, ``namespace-alias``,
  ``fallback``, simplified literal-result-element stylesheets, ``xsl:import`` with import precedence (resolved against a
  ``base_url``), ``cdata-section-elements``, and the ``xml``/``html``/``text`` output methods (html auto-selected for a
  null-namespace ``html`` root, with ``<meta>`` injection). Validated against libxslt's XSLT 1.0 Recommendation corpus
  at 76 of 79 cases byte-for-byte; the three remaining need a locale-collation, DTD, or XPath-namespace-axis layer
  turbohtml does not carry. (:issue:`537`)
- :meth:`turbohtml.Node.canonicalize` serializes a subtree to Canonical XML (c14n), the byte-exact form an XML signature
  signs. A :class:`turbohtml.Canonical` config selects the algorithm: Canonical XML 1.0 or 1.1, the exclusive variant
  that renders only the namespaces a subtree visibly uses, the with-comments variant, and an ``inclusive_ns_prefixes``
  prefix list for exclusive mode. Attributes are reordered (namespace declarations first, then by namespace URI and
  local name), redundant namespace declarations are dropped, empty elements are written as start-end pairs, and
  character references are normalized, matching ``lxml``'s ``tostring(method="c14n")`` byte-for-byte over the same
  infoset. (:issue:`538`)
- :class:`turbohtml.validate.XMLSchema` and :class:`turbohtml.validate.RelaxNG` validate a document parsed with
  :func:`turbohtml.parse_xml` against an XSD 1.0 or RELAX NG schema, mirroring lxml's ``etree.XMLSchema`` /
  ``etree.RelaxNG``. A schema compiles once in the C core and each :meth:`~turbohtml.validate.XMLSchema.validate`
  returns a :class:`~turbohtml.validate.ValidationResult` -- a ``valid`` flag plus one
  :class:`~turbohtml.validate.ValidationError` per violation, each with the document-order path that located it. XSD
  covers the element/attribute declarations, the sequence/choice/all content models with ``minOccurs``/``maxOccurs``,
  references, complex/simple types with extension, the built-in datatypes, and the constraining facets; RELAX NG covers
  the full XML-syntax pattern set (including ``interleave``) through the derivative algorithm. (:issue:`539`)
- :func:`turbohtml.parse_xml` parses a document under XML 1.0 well-formedness instead of the WHATWG HTML tree builder,
  returning the same navigable :class:`~turbohtml.Document`. Names stay case-sensitive, ``<x/>`` self-closes any
  element, CDATA sections and processing instructions become :class:`~turbohtml.CData` and
  :class:`~turbohtml.ProcessingInstruction` nodes, only the five predefined entities and numeric references resolve, and
  a namespace prefix must be declared with ``xmlns``. Names follow the exact XML 1.0 ``NameStartChar`` /``NameChar``
  productions, and the Namespaces in XML 1.0 well-formedness constraints hold in full: the reserved ``xml`` and
  ``xmlns`` prefixes and their namespace names cannot be rebound, a prefix declaration cannot be empty, a
  processing-instruction target carries no colon, and no two attributes share an expanded name. There is no HTML
  recovery: the first well-formedness violation -- a mismatched or unclosed tag, an undeclared prefix, an undefined
  entity, a duplicate attribute -- raises :exc:`~turbohtml.HTMLParseError`. This is the equivalent of
  ``lxml.etree.fromstring`` / ``etree.XMLParser`` over turbohtml's dependency-free, fully typed node API. (:issue:`540`)
- Added an HTML5 authoring-conformance checker with a severity model. :func:`turbohtml.conformance.check` walks a parsed
  document and returns a :class:`~turbohtml.conformance.ConformanceReport` -- a ``valid`` verdict plus every
  :class:`~turbohtml.conformance.ConformanceMessage`, each carrying a stable ``code``, a ``severity`` (``"error"``,
  ``"warning"``, or ``"info"``), a human-readable message, and a source line and column. It flags the
  document-conformance requirements the parser does not raise as a :class:`~turbohtml.ParseError`: a missing ``img``
  alt, obsolete presentational elements and attributes, duplicate ids, invalid or redundant ARIA roles, empty headings,
  a ``section`` without a heading, and a document with no title or ``lang``. The document is valid exactly when nothing
  is an error, so warnings and info notes never change the verdict. The whole walk runs in the C core against the WHATWG
  authoring rules and WAI-ARIA 1.2, the model the Nu Html Checker (validator.nu) uses;
  :func:`~turbohtml.conformance.check_html` parses a markup string first. (:issue:`541`)
- :meth:`~turbohtml.Node.xpath` gained the string subset of XPath 2.0: ``ends-with``, ``string-join(seq, sep)``,
  ``lower-case`` and ``upper-case`` (Unicode case mapping), and the regex ``matches(input, pattern[, flags])`` and
  ``replace(input, pattern, repl[, flags])`` spellings, where ``replace`` reads ``$1``-style group references and
  rewrites every match. They dispatch in the compiled-C engine alongside the XPath 1.0 core and the EXSLT namespaces, so
  an expression ported from ``elementpath``, ``lxml``, or ``htmlquery`` that leans on them runs without registration.
  (:issue:`542`)
- :func:`turbohtml.detect.normalize` returns text in a Unicode normalization form (UAX #15) -- ``NFC``, ``NFD``,
  ``NFKC``, or ``NFKD`` -- the C successor to :func:`python:unicodedata.normalize`, and
  :func:`turbohtml.detect.is_normalized` tests membership. Both run over tables generated from the interpreter's own
  ``unicodedata``, so they agree with it exactly, and a quick check returns already-normalized text without allocating.
  (:issue:`543`)
- :func:`turbohtml.rewrite.rewrite` transforms HTML in a single streaming pass without building a tree, the model
  Cloudflare's lol-html popularized. It runs the WHATWG tokenizer over the input while tracking only the open-element
  stack, hands each element a CSS selector matches -- and, on request, each run of text, each comment, and the doctype
  -- to a Python handler that edits it in place (set or remove an attribute, insert markup before, after, or around it,
  replace its inner content, unwrap it, or drop it), and emits the result incrementally. Working memory stays
  proportional to the open-element depth, not the document size, so a multi-megabyte page rewrites in a fixed footprint,
  and an untouched construct is reproduced verbatim. Because the pass never looks ahead, the matchable selector subset
  is the one decidable from an element and its ancestors -- type, universal, id, class, and attribute selectors, the
  descendant and child combinators, ``:root``, and ``:is()``/``:where()``/``:not()`` over that subset; a sibling
  combinator, a positional or structural pseudo-class, or ``:has()`` raises :class:`~turbohtml.SelectorSyntaxError`.
  (:issue:`544`)
- A new :mod:`turbohtml.treebuild` module retargets the parser at a tree of your own.
  :func:`turbohtml.treebuild.parse_into` runs the WHATWG tree builder and drives a builder object -- a ``create_*``
  method per node kind plus an ``append`` that links a child under its parent -- to construct the tree directly,
  returning whatever the builder made its document root. No navigable :class:`turbohtml.Node` is materialized and the
  tree is walked only once, so an index, a diff tree, or another library's nodes is populated straight from the parse
  rather than by a second descent. Each element carries its namespace URI and its attributes as ``(name, value)`` pairs,
  a ``<template>``'s content is appended under the template handle, and a bogus ``<?...>`` construct reaches a distinct
  ``create_pi``. This is Rust html5ever's ``TreeSink`` and Node parse5's ``TreeAdapter`` in turbohtml shape; the tree
  construction, the walk, and the string extraction all run in C. (:issue:`545`)
- :mod:`turbohtml.cssom` runs the CSS Object Model cascade: :func:`~turbohtml.cssom.computed_style` resolves the
  ``getComputedStyle`` of an element by collecting every ``<style>`` sheet plus the inline ``style`` along its ancestor
  chain, matching the native selector engine, ordering the declarations by origin importance, the style attribute,
  specificity, and source order, then applying inheritance, shorthand expansion, and each property's initial value --
  all in the C core under the per-tree critical section. Alongside it, :class:`~turbohtml.cssom.StyleSheet`,
  :class:`~turbohtml.cssom.RuleList`, :class:`~turbohtml.cssom.StyleRule`, and
  :class:`~turbohtml.cssom.StyleDeclaration` are the read-only, turbohtml-native spelling of the CSSOM ``CSSStyleSheet``
  / ``CSSRuleList`` / ``CSSStyleRule`` / ``CSSStyleDeclaration`` interfaces. The returned value is the computed value,
  not the used value: turbohtml runs no layout, so lengths and percentages come back as written, the same boundary jsdom
  and cssstyle draw. Shorthand expansion covers the distributive families (``margin``, ``padding``,
  ``border-width``/``style``/``color``, ``overflow``) and the ``<line-width> || <line-style> || <color>`` shorthands
  ``border``, each ``border-<side>``, and ``outline``, whose components resolve in any order and reset every longhand
  they cover. (:issue:`546`)
- :meth:`turbohtml.Node.to_source` losslessly serializes a tree back to HTML, re-emitting the verbatim source bytes of
  every element and text run a parse left untouched and reserializing only the parts a mutation changed. Parse with
  ``source_locations=True`` and an unedited round trip reproduces the input byte for byte -- author quoting, tag-name
  case, character-reference spelling, and insignificant whitespace intact -- for markup that parsed without implied
  elements or content reordering; after an edit only the changed node's markup is rewritten while every untouched
  sibling and subtree keeps its original span. It is the tree-based counterpart to the streaming
  :func:`turbohtml.rewrite.rewrite`, the model Cloudflare's lol-html popularized. (:issue:`547`)
- :func:`turbohtml.parse`, :func:`turbohtml.parse_fragment`, and :class:`~turbohtml.IncrementalParser` gained a
  ``source_locations`` flag (default ``False``) that records the granular source spans parse5 exposes as
  ``sourceCodeLocationInfo``. With it on, each element's :attr:`~turbohtml.Node.source_location` returns a
  :class:`~turbohtml.SourceLocation` giving the :class:`~turbohtml.SourceSpan` of its start tag, its end tag (``None``
  when the source never closed it), and each attribute's whole ``name="value"``, every span carrying start/end line,
  column, and code-point offset so ``source[start_offset:end_offset]`` slices the construct out. The tokenizer stamps
  the spans in C as it runs and the tree builder hangs the record off each element, so the feature is zero-overhead when
  off; it implies ``positions`` when on, keeping :attr:`~turbohtml.Node.source_line` and
  :attr:`~turbohtml.Node.position` available beside the spans. (:issue:`548`)
- Added declarative Shadow DOM to the parser. When the tree builder meets a ``<template>`` carrying a ``shadowrootmode``
  of ``open`` or ``closed`` on a valid shadow host, it attaches a shadow root to the template's parent and parses the
  template's content into it, reusing the Shadow DOM tree model -- the template element never joins the light tree.
  ``shadowrootdelegatesfocus`` and ``shadowrootclonable`` set the matching flags, readable as the new
  :attr:`~turbohtml.ShadowRoot.delegates_focus` and :attr:`~turbohtml.ShadowRoot.clonable` properties. Following the
  WHATWG per-document flag, :func:`turbohtml.parse` honors declarative shadow roots by default (a browser navigation)
  while :func:`turbohtml.parse_fragment` does not (an ``innerHTML`` assignment); the new
  ``allow_declarative_shadow_roots`` argument flips either default, matching ``setHTMLUnsafe`` when turned on for a
  fragment. (:issue:`549`)
- Added the DOM Living Standard traversal objects :class:`turbohtml.TreeWalker` and :class:`turbohtml.NodeIterator`,
  with the :class:`turbohtml.NodeFilter` constants for the ``what_to_show`` bitmask and the filter verdicts. A
  ``TreeWalker`` is a movable cursor over a subtree -- ``parent_node``, ``first_child``, ``last_child``,
  ``next_sibling``, ``previous_sibling``, ``next_node``, ``previous_node`` -- while a ``NodeIterator`` is the flat,
  filtered forward/backward view and iterates directly in a ``for`` loop. Both take a ``what_to_show`` node-type mask
  and an optional filter callback returning ``FILTER_ACCEPT``, ``FILTER_REJECT``, or ``FILTER_SKIP``; reject drops a
  node and its whole subtree while skip drops only the node, so a ``TreeWalker`` prunes where a ``NodeIterator`` (having
  no subtree) treats the two alike. The state machine and the ``what_to_show`` test run in the C core; the filter is the
  one callback into Python. This ports traversal code written against the browser DOM or jsdom. (:issue:`550`)
- :func:`turbohtml.parse` and :func:`turbohtml.parse_fragment` gained a ``scripting`` flag (default ``False``). With it
  on, turbohtml sets the WHATWG scripting flag: ``<noscript>`` becomes a raw-text element, so its content is one text
  run rather than parsed markup and serializes back unescaped, reproducing the tree a scripting browser builds. The flag
  is a property of the parsed tree, so the serializer and ``inner_html`` stay consistent with how it was parsed. parse5
  and html5ever default this on for browser fidelity; turbohtml keeps it off so ``<noscript>`` fallback content stays
  navigable. (:issue:`551`)
- Added the DOM Living Standard :class:`~turbohtml.Range` and :class:`~turbohtml.StaticRange` types. A ``Range`` holds
  two boundary points -- each a ``(container, offset)`` pair -- and carries the full boundary API
  (:meth:`~turbohtml.Range.set_start`/:meth:`~turbohtml.Range.set_end` and their ``_before``/``_after`` variants,
  :meth:`~turbohtml.Range.select_node`, :meth:`~turbohtml.Range.select_node_contents`,
  :meth:`~turbohtml.Range.collapse`), the derived :attr:`~turbohtml.Range.collapsed` and
  :attr:`~turbohtml.Range.common_ancestor_container` properties, the comparisons
  (:meth:`~turbohtml.Range.compare_boundary_points`, :meth:`~turbohtml.Range.compare_point`,
  :meth:`~turbohtml.Range.is_point_in_range`, :meth:`~turbohtml.Range.intersects_node`), and the content operations
  (:meth:`~turbohtml.Range.clone_contents`, :meth:`~turbohtml.Range.extract_contents`,
  :meth:`~turbohtml.Range.delete_contents`, :meth:`~turbohtml.Range.insert_node`,
  :meth:`~turbohtml.Range.surround_contents`, :meth:`~turbohtml.Range.clone_range`), each following the WHATWG
  boundary-point ordering and extract/clone/delete algorithms in C under the per-tree critical section. ``StaticRange``
  is the immutable four-value snapshot. Offsets index code points in character data and children elsewhere, so a Python
  string's own indexing lines up with a text-node offset. (:issue:`552`)
- Added the DOM Living Standard Shadow DOM tree model. :meth:`~turbohtml.Element.attach_shadow` attaches an open or
  closed shadow tree and returns a :class:`~turbohtml.ShadowRoot` -- a document-fragment-like root held off the light
  tree, so it never appears among the host's children or in its serialization -- reachable through
  :attr:`~turbohtml.Element.shadow_root` (``None`` for a closed root) and carrying :attr:`~turbohtml.ShadowRoot.mode`,
  :attr:`~turbohtml.ShadowRoot.host`, :meth:`~turbohtml.ShadowRoot.set_inner_html`, and
  :meth:`~turbohtml.ShadowRoot.append`. ``<slot>`` elements assign the host's children by name (the unnamed default slot
  takes the rest): :meth:`~turbohtml.Element.assigned_nodes` and :meth:`~turbohtml.Element.assigned_elements` read what
  a slot received, with a ``flatten`` option that falls back to a slot's own children and expands nested shadow slots,
  and :attr:`~turbohtml.Node.assigned_slot` gives the slot a child landed in. :attr:`~turbohtml.Node.flattened_children`
  returns the composed tree with every slot replaced by its assigned nodes. The assignment and flattening algorithms run
  in C under the per-tree critical section and are computed on demand, so they always reflect the current tree.
  (:issue:`553`)
- Added :class:`~turbohtml.MutationObserver`, a synchronous take on the DOM ``MutationObserver`` for recording tree
  edits. Register a node with :meth:`~turbohtml.MutationObserver.observe` and the DOM options (``child_list``,
  ``attributes``, ``character_data``, ``subtree``, ``attribute_old_value``, ``character_data_old_value``,
  ``attribute_filter``); every change made through the mutation API queues a :class:`~turbohtml.MutationRecord` carrying
  the added and removed nodes, the surrounding siblings, and the attribute name and old value when asked, following the
  WHATWG "queue a mutation record" algorithm in C under the per-tree critical section. Because turbohtml has no event
  loop, delivery is synchronous rather than microtask-scheduled: :meth:`~turbohtml.MutationObserver.take_records`
  returns and clears the queued batch, and :meth:`~turbohtml.MutationObserver.deliver` drains it and calls the
  observer's callback. :meth:`~turbohtml.MutationObserver.disconnect` stops observing and discards pending records.
  (:issue:`554`)
- :class:`~turbohtml.clean.Policy` gained ``xml``: with it on, the sanitizer serializes the cleaned tree as well-formed
  XML/XHTML instead of HTML. Every kept empty element self-closes (``<br/>``), foreign SVG and MathML subtrees declare
  their namespace, text and attribute values follow the XML escaping rules, and a kept comment, a control character
  outside XML's ``Char`` production, or an attribute name XML cannot hold is neutralized, so the output always reparses
  through :func:`turbohtml.parse_xml`. The walk and the safety baseline are unchanged, so an XML-mode policy is exactly
  as safe as its HTML-mode twin. This clones DOMPurify's ``PARSER_MEDIA_TYPE: 'application/xhtml+xml'`` and replaces the
  brittle ``.replace("<br>", "<br/>")`` a bleach-based cleaner needs to feed a strict XHTML consumer such as Reportlab's
  RML. :attr:`turbohtml.Node.inner_xml` exposes the same children-only XML serialization for any node. (:issue:`565`)
- The ``rewrite`` benchmark now runs against a fair in-process peer. lxml and BeautifulSoup do the same edits --
  ``rel=nofollow`` on every link, ``loading=lazy`` on every image, every comment dropped -- through the parse, mutate,
  and serialize round trip that :func:`turbohtml.rewrite.rewrite` skips, and the table reports each party's peak
  resident memory beside throughput, so the tree the streaming rewriter never builds shows up as memory it never holds.
  The :doc:`lol-html migration guide </migration/lol-html>` carries the numbers. (:issue:`612`)

*********************
 v1.0.0 (2026-07-05)
*********************

The 1.0 release finishes the native-C port, settles one canonical public API, and closes the feature gap against the
libraries turbohtml replaces. The notes below fold the whole 0.4.0 to 1.0.0 span into one overview; the anchor issues
point at the epics behind each theme.

Backward incompatible changes - 1.0.0
=====================================

- Give the public surface one name per concept. CSS matching folds from ``turbohtml.match`` into :mod:`turbohtml.query`;
  the sanitizer, linkifier, and every minifier gather under :mod:`turbohtml.clean`; a malformed selector raises one
  :class:`turbohtml.SelectorSyntaxError` from every parse path; the two ``Detector`` classes split into
  :class:`turbohtml.detect.EncodingDetector` and :class:`turbohtml.clean.LinkDetector`; and each surface with more than
  six arguments takes one frozen ``options`` config. (:issue:`478`)
- Select a serialization mode with a single ``layout`` argument in place of ``indent``, so ``serialize(indent=2)``
  becomes ``serialize(layout=Indent(2))`` and :class:`~turbohtml.Minify` selects minified output. (:issue:`171`)
- Report a valueless attribute (``<x a>``) as the empty string rather than ``None`` in :attr:`turbohtml.Element.attrs`,
  matching the WHATWG tokenizer and the DOM. (:issue:`87`)

Features - 1.0.0
================

- Query a tree with the full Selectors Level 4 grammar (``:is()``, ``:where()``, ``:has()``, ``:not()``,
  ``:nth-child(An+B of S)``, the structural, input, ``:lang()``, ``:dir()``, and ``:scope`` pseudo-classes) and an XPath
  1.0 engine: :meth:`~turbohtml.Node.xpath`, a compiled reusable :class:`turbohtml.XPath`, the EXSLT function set, and
  namespace, variable, and extension binding. A pyquery-style :class:`turbohtml.query.Query`, a soupsieve-shaped
  matcher, and :func:`turbohtml.convert.css_to_xpath` cover the BeautifulSoup, cssselect, parsel, and pyquery surfaces.
  (:issue:`179`)
- Serialize back to HTML with pretty-print, whitespace minification, and lazy streaming
  (:meth:`~turbohtml.Node.serialize_iter`), and minify HTML, CSS, and JavaScript through native engines under
  :mod:`turbohtml.clean`. Every transform is round-trip safe, replacing rcssmin, csscompressor, rjsmin, jsmin,
  minify-html, and htmlmin. (:issue:`343`, :issue:`346`)
- Convert a tree to GitHub-Flavored Markdown, layout-aware text, or annotated ``(start, end, label)`` spans, and extract
  a page's main article, boilerplate paragraphs, publication date, tables, links, and structured data (JSON-LD,
  Microdata, RDFa, Dublin Core, Open Graph) through :mod:`turbohtml.extract`, replacing markdownify, html2text,
  inscriptis, trafilatura, readability, htmldate, extruct, and microdata. (:issue:`273`, :issue:`276`)
- Detect a byte stream's encoding and a text's natural language from the standalone :mod:`turbohtml.detect` module,
  which reports confidence and a BOM label, covers 69 languages across nine scripts, and replaces chardet,
  charset-normalizer, and cchardet. (:issue:`315`, :issue:`474`)
- Parse incrementally from a stream with :class:`turbohtml.IncrementalParser`, read the WHATWG parse errors recovery
  swallows through :attr:`~turbohtml.Document.errors`, and locate each element in the source through
  :attr:`~turbohtml.Node.source_line` and :attr:`~turbohtml.Node.source_col`. (:issue:`210`, :issue:`212`)
- Sanitize untrusted HTML against a frozen allowlist :class:`turbohtml.clean.Policy` that is safe with no arguments and
  scrubs inline and embedded CSS, foreign namespaces, and media hosts, and auto-link URLs and email addresses, together
  replacing bleach. (:issue:`8`, :issue:`9`)
- Build and edit the tree in place: construct nodes and a whole HTML5 page with :data:`turbohtml.build.E` and
  :func:`turbohtml.build.document`, edit the class token set and inner HTML or text, wrap and unwrap subtrees, trim a
  document to a selector with :meth:`~turbohtml.Node.prune`, read and fill form fields, and compare two subtrees with
  :meth:`~turbohtml.Node.equals`. (:issue:`275`, :issue:`225`, :issue:`468`)
- Clean, canonicalize, and extract page URLs through :mod:`turbohtml.extract`, backed by a native URL pipeline (WHATWG
  splitting, percent-coding, relative-reference joining, UTS #46 IDNA, and Public Suffix List registrable-domain
  filtering), and run the toolkit from a ``turbohtml`` command line covering minify, detect, to-markdown, to-text, and
  sanitize. (:issue:`321`, :issue:`470`)

Bug fixes - 1.0.0
=================

- Bring tree construction to WHATWG conformance across foster parenting, foreign content, the select, table, and
  template insertion modes, doctype and quirks detection, duplicate and void-element handling, validated against the
  html5lib-tests corpus. (:issue:`32`)
- Resolve every label in the WHATWG Encoding Standard, decode the replacement and gb18030 families and the windows-1252
  C1 bytes, and honor the 1024-byte ``<meta>`` prescan. (:issue:`54`, :issue:`423`)
- Match the Selectors Level 4 corrections: forgiving ``:is()``/``:where()`` lists, quirks-mode case folding, CSS escape
  decoding, namespace prefixes, whitespace-only ``:empty``, and ``:scope`` resolution inside ``:has()``. (:issue:`174`)
- Fix XPath 1.0 semantics: shortest round-tripping number formatting, half-to-positive-infinity rounding, fixed function
  arity, node-set typing, and arena-safe predicate compilation. (:issue:`398`)
- Correct the Markdown and text exporters on nested and loose lists, link and image escaping, the ``<pre>`` leading
  newline, ordinal ``<li value>``, and raw-text suppression in every namespace. (:issue:`384`)
- Fix extraction on landmark-wrapped and list-structured articles, Microdata ``itemref`` merging, table ``rowspan``
  bounds, and the WHATWG form ``select``/``optgroup`` submission rules. (:issue:`385`, :issue:`408`)
- Keep the CSS and JavaScript minifiers value-safe: ``calc()`` type mixing, duplicate-declaration fallbacks,
  ``currentcolor``, conditional folding, and adjacent-string-literal concatenation. (:issue:`415`)
- Raise a precise, typed error from every public failure path in place of a silent wrong result or a leaked low-level
  type, and document each callable's exceptions. (:issue:`434`)

Improved documentation - 1.0.0
==============================

- Ship a migration guide for each library turbohtml replaces, every one carrying a monthly-downloads badge, a measured
  benchmark, and a speed-up multiplier, with the index ordered by adoption. (:issue:`313`)
- Restructure the reference, how-to, and migration trees around the eight-namespace taxonomy (parse/DOM, detect, query,
  clean, convert, extract, build, serialize), and add ``llms.txt`` maps, a sitemap, and per-page meta descriptions.
  (:issue:`478`)
- Add a written security policy, a "How turbohtml was built" page, and the seven design principles that shape the
  library. (:issue:`500`)

Packaging updates - 1.0.0
=========================

- Build the release wheels with profile-guided, link-time optimization trained offline over a real-world corpus of
  clean, malformed, legacy-encoded, and structured-data markup. (:issue:`481`)
- Pin every network-sourced C data table (IANA TLDs, the Public Suffix List, and the Unicode IDNA and NFC tables) to a
  named source commit and a SHA-256 checksum, so a rebuild is reproducible and aborts on a poisoned upstream.
  (:issue:`478`)
- Strip the compiled extension's local symbol table from the release wheels at link time, trimming about 65 KB from the
  Linux ``.so`` and 46 KB from the macOS bundle; the source distribution still carries every test, tool, and generated
  table needed to build from source. (:issue:`478`)

Miscellaneous internal changes - 1.0.0
======================================

- Finish the native-C port: URL splitting, percent-coding, relative joining, IDNA, registrable-domain lookup, and date
  parsing move from ``urllib``, ``re``, and ``datetime`` into the C extension, leaving Python a thin configure-and-wrap
  shim. (:issue:`478`)
- Speed the read path: a per-tree atom index runs a tag-pinned :meth:`~turbohtml.Node.find` several times faster,
  ``:has()`` evaluates in one amortized-linear pass, streaming serialization sizes its buffer up front, and link-time
  optimization re-inlines across a subsystem-first C layout. (:issue:`162`, :issue:`509`)
- Harden against untrusted input: ASan and UBSan fuzz gates on every entry point, a DOMPurify XSS oracle and an
  html5lib-tests tree-equality oracle over the sanitizer, mutation-XSS namespace checks, caps on element nesting and
  duplicate attributes, and one overflow-safe buffer-growth helper across the C core. (:issue:`503`, :issue:`511`)
- Validate free-threaded safety under pytest-run-parallel and ThreadSanitizer, and gate performance on every pull
  request with a per-operation CodSpeed benchmark over the real corpora. (:issue:`380`)

*********************
 v0.4.0 (2026-06-16)
*********************

Features - 0.4.0
================

- Build and edit the tree, not just read it: construct :class:`~turbohtml.Element`, :class:`~turbohtml.Text`, and
  :class:`~turbohtml.Comment` nodes and rearrange them with the full set of insert, wrap, extract, and normalize
  methods, with :attr:`~turbohtml.Element.attrs` and ``.text``/``.data`` as live setters. ``copy``, ``deepcopy``, and
  ``pickle`` duplicate a subtree - by :user:`gaborbernat`. (:issue:`19`)
- Round out the node model: :class:`~turbohtml.ProcessingInstruction` and :class:`~turbohtml.CData` join the hierarchy,
  :class:`~turbohtml.Doctype` exposes its :attr:`~turbohtml.Doctype.public_id` and :attr:`~turbohtml.Doctype.system_id`,
  and every node type supports structural pattern matching - by :user:`gaborbernat`. (:issue:`22`)

Improved documentation - 0.4.0
==============================

- Learn the write path through new tutorial, how-to, and explanation docs, backed by benchmarks showing turbohtml builds
  and rewrites trees about twice as fast as `lxml <https://lxml.de/>`__ and an order of magnitude faster than
  `BeautifulSoup <https://www.crummy.com/software/BeautifulSoup/>`__ - by :user:`gaborbernat`. (:issue:`19`)
- Port to turbohtml with migration guides from `BeautifulSoup <https://www.crummy.com/software/BeautifulSoup/>`__, `lxml
  <https://lxml.de/>`__, `selectolax <https://github.com/rushter/selectolax>`__, `html5lib
  <https://github.com/html5lib/html5lib-python>`__, and the standard library, each mapping the source library's idioms
  to their turbohtml equivalents and flagging behavior differences - by :user:`gaborbernat`. (:issue:`23`)

*********************
 v0.3.0 (2026-06-16)
*********************

Features - 0.3.0
================

- Query any node with CSS through :meth:`~turbohtml.Node.select` and :meth:`~turbohtml.Node.select_one`, a native
  matcher covering type, universal, ``#id``, ``.class``, and attribute selectors (all operators plus the
  case-sensitivity flag) across the descendant, child, adjacent, and sibling combinators, returning comma groups in
  document order. An invalid selector raises ``ValueError`` - by :user:`gaborbernat`. (:issue:`14`)
- Search with a richer :meth:`~turbohtml.Node.find` and :meth:`~turbohtml.Node.find_all` filter grammar: match the tag
  and attributes by string, regex, bool, callable, or list (including ``class_`` and the ``attrs`` mapping), and choose
  the search direction with the ``axis`` keyword. ``find_all`` takes a ``limit`` and returns a ``list`` - by
  :user:`gaborbernat`. (:issue:`15`)
- Test a node against a selector with :meth:`~turbohtml.Node.matches` and :meth:`~turbohtml.Node.closest`: ``matches()``
  reports whether the node satisfies a CSS selector in context, and ``closest()`` returns the nearest matching ancestor
  (or the node itself), or ``None`` - by :user:`gaborbernat`. (:issue:`16`)
- Walk the tree by axis with new iterators: :attr:`~turbohtml.Node.next_siblings`,
  :attr:`~turbohtml.Node.previous_siblings`, document-order :attr:`~turbohtml.Node.following` and
  :attr:`~turbohtml.Node.preceding`, plus the :attr:`~turbohtml.Node.strings` and
  :attr:`~turbohtml.Node.stripped_strings` text iterators - by :user:`gaborbernat`. (:issue:`17`)
- Read HTML token-list attributes (``class``, ``rel``, ``headers``, ``sizes``, ``sandbox``, and the rest) as a
  ``list[str]`` in :attr:`turbohtml.Element.attrs`, split on ASCII whitespace; other attributes stay strings and
  valueless ones stay ``None`` - by :user:`gaborbernat`. (:issue:`18`)
- Control serialization on any node: :attr:`~turbohtml.Node.inner_html` returns the children, while
  :meth:`~turbohtml.Node.serialize` and :meth:`~turbohtml.Node.encode` take a ``formatter`` (the
  :class:`~turbohtml.Formatter` enum picks the escape policy) and an ``indent`` for pretty output. The default stays
  WHATWG-conformant HTML - by :user:`gaborbernat`. (:issue:`20`)
- Parse ``bytes`` directly: :func:`turbohtml.parse` sniffs the encoding with the WHATWG algorithm (BOM, ``encoding``
  argument, ``<meta>`` charset, then windows-1252), decodes with U+FFFD replacement, and reports the result in
  :attr:`~turbohtml.Document.encoding` - by :user:`gaborbernat`. (:issue:`21`)

*********************
 v0.2.0 (2026-06-11)
*********************

Features - 0.2.0
================

- Tokenize HTML directly with a WHATWG-conformant tokenizer: :func:`turbohtml.tokenize` for whole strings, the streaming
  :class:`turbohtml.Tokenizer`, and the :class:`turbohtml.Token` / :class:`turbohtml.TokenType` types, validated against
  the html5lib-tests tokenizer conformance suite. (:issue:`6`)
- Run :func:`turbohtml.escape` and :func:`turbohtml.unescape` faster: vectorized scanning and bulk copying speed up both
  calls, with unescaping of real escaped HTML about three times faster than the general lookup path. The benchmark now
  uses `pyperf <https://pyperf.readthedocs.io>`_ over multi-MiB real documents - by :user:`gaborbernat`. (:issue:`7`)

*********************
 v0.1.1 (2026-06-09)
*********************

Packaging updates - 0.1.1
=========================

- Install reliably from PyPI again: publishing each wheel in its own job keeps PEP 740 attestations within the Sigstore
  identity's lifetime, fixing the ``sigstore.oidc.ExpiredIdentity`` failure that blocked the first upload - by
  :user:`gaborbernat`. (:issue:`4`)

*********************
 v0.1.0 (2026-06-09)
*********************

Features - 0.1.0
================

- Speed up entity handling with C-accelerated :func:`turbohtml.escape` and :func:`turbohtml.unescape`, drop-in
  replacements for :func:`python:html.escape` and :func:`python:html.unescape`, shipped as wheels for CPython 3.10
  through 3.15 - by :user:`gaborbernat`. (:issue:`1`)
- Escape non-ASCII text that needs no escaping several times faster with a vectorized special-character scan, ahead of
  :func:`python:html.escape` - by :user:`gaborbernat`. (:issue:`3`)

Improved documentation - 0.1.0
==============================

- See the measured :func:`turbohtml.escape`/:func:`turbohtml.unescape` speedups in the README and docs, reproduce them
  with ``tox -e bench``, and browse a typed API reference with intersphinx links - by :user:`gaborbernat`. (:issue:`2`)

Miscellaneous internal changes - 0.1.0
======================================

- Automate releases with git-tag-derived versioning, a towncrier-managed changelog, and a prepare-release workflow that
  tags and triggers the trusted-publishing wheel build - by :user:`gaborbernat`. (:issue:`1`)
