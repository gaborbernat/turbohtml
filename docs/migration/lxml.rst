.. _migration-lxml:

###########
 From lxml
###########

.. image:: https://static.pepy.tech/badge/lxml
    :alt: lxml downloads
    :target: https://pepy.tech/project/lxml

`lxml <https://lxml.de>`_ is the libxml2/libxslt binding that most Python HTML and XML processing has been built on:
``lxml.html`` parses documents into ElementTree-style elements with ``.text``/``.tail`` strings, and the wider stack
adds XPath, XSLT, and schema validation.

***************
 Why turbohtml
***************

:func:`turbohtml.parse` builds the WHATWG document tree that libxml2's HTML parser does not, returns a fully type
annotated :class:`~turbohtml.Document`, and folds XPath, CSS, and the ``find``/``find_all`` grammar into one node API
instead of separate ``findall``/``xpath``/``cssselect`` entry points. It parses two to four times faster than lxml while
matching a browser on malformed input:

.. list-table::
    :header-rows: 1
    :widths: 40 20 20 20

    - - parse
      - turbohtml
      - lxml
      - speed-up
    - - wpt page (4 kB)
      - 11.4 µs
      - 27.1 µs
      - 2.4x
    - - wpt page (92 kB)
      - 272 µs
      - 631 µs
      - 2.3x
    - - whatwg spec (235 kB)
      - 518 µs
      - 1.22 ms
      - 2.4x
    - - ecmascript spec (3 MB)
      - 4.54 ms
      - 17.4 ms
      - 3.8x

The :doc:`/development/performance` page also benchmarks turbohtml's serializer, builder, editor, CSS, and XPath 1.0
engine against lxml directly.

*************
 The renames
*************

:func:`turbohtml.parse` replaces ``lxml.html.document_fromstring`` and returns a :class:`~turbohtml.Document`;
:func:`turbohtml.parse_fragment` replaces ``lxml.html.fromstring`` for a fragment. The biggest change is the tree shape:
lxml stores text as an element's ``.text`` and ``.tail`` strings, while turbohtml models it as real child
:class:`~turbohtml.Text` nodes, so you iterate children instead of reading two string fields.

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - lxml
      - turbohtml
    - - ``el.tag``
      - :attr:`~turbohtml.Element.tag` (same)
    - - ``el.get("x")``, ``el.attrib``, ``el.set("x", "v")``
      - :attr:`~turbohtml.Element.attrs` (``attrs.get("x")``, ``attrs["x"] = "v"``)
    - - ``el.classes.add("x")``, ``el.classes.discard("x")``, ``el.classes.toggle("x")``, ``"x" in el.classes``
      - :meth:`el.add_class("x") <turbohtml.Element.add_class>`, :meth:`el.remove_class("x")
        <turbohtml.Element.remove_class>`, :meth:`el.toggle_class("x") <turbohtml.Element.toggle_class>`,
        :meth:`el.has_class("x") <turbohtml.Element.has_class>`
    - - ``el.text``, ``el.tail``
      - child :class:`~turbohtml.Text` nodes; iterate :attr:`~turbohtml.Node.children`
    - - ``el.text_content()``
      - :attr:`~turbohtml.Node.text`
    - - ``el.getparent()``, ``el.getnext()``, ``el.getprevious()``
      - :attr:`~turbohtml.Node.parent`, :attr:`~turbohtml.Node.next_sibling`, :attr:`~turbohtml.Node.previous_sibling`
    - - ``list(el)``, ``el.iterdescendants()``, ``el.iterancestors()``
      - :attr:`~turbohtml.Node.children`, :attr:`~turbohtml.Node.descendants`, :attr:`~turbohtml.Node.ancestors`
    - - ``el.findall(".//a")``, ``el.xpath("//a[@href]")``
      - :meth:`~turbohtml.Node.find_all`, :meth:`~turbohtml.Node.xpath`
    - - ``etree.XPath("//a[@href=$u]")(el, u=v)``
      - :class:`~turbohtml.XPath` (``XPath("//a[@href=$u]")(el, u=v)``)
    - - ``el.cssselect("div a")``
      - :meth:`~turbohtml.Node.select`
    - - ``lxml.html.Element("div")``, ``etree.SubElement(p, "div")``
      - :class:`~turbohtml.Element`, :meth:`p.append(Element("div")) <turbohtml.Element.append>`
    - - ``el.drop_tag()``, ``el.drop_tree()``
      - :meth:`~turbohtml.Node.unwrap`, :meth:`~turbohtml.Node.decompose`
    - - ``el.sourceline``
      - :attr:`~turbohtml.Node.source_line` (1-based, like lxml; plus :attr:`~turbohtml.Node.source_col`)
    - - ``el.iterlinks()``
      - :meth:`~turbohtml.Node.links`
    - - ``el.make_links_absolute(base)``, ``el.rewrite_links(fn)``
      - :meth:`~turbohtml.Node.resolve_links`, :meth:`~turbohtml.Node.rewrite_links`
    - - ``lxml.html.tostring(el)``
      - :attr:`~turbohtml.Node.html`

.. testcode::

    doc = parse('<div><a href="/x">go</a></div>')
    print(doc.find_all("a", attrs={"href": True}))
    print(doc.select_one("div a").attrs["href"])

.. testoutput::

    [Element('a')]
    /x

*************
 Performance
*************

When one expression runs against many nodes, precompile it once with :class:`~turbohtml.XPath` instead of calling
:meth:`~turbohtml.Node.xpath`, which reparses the expression on every call. This is the same move as reaching for
``lxml.etree.XPath`` over a bare ``el.xpath``: the parse happens at construction, and the call site only supplies the
context node and any ``$name`` variables. turbohtml's compiled program is tree-independent, so a single object evaluates
against many documents, and it stays ahead of lxml per evaluation. The numbers below are for ``//a[@href]`` over the 9.6
kB wpt page from the :doc:`/development/performance` benchmark (``tox -e bench xpath``):

.. list-table::
    :header-rows: 1
    :widths: 40 20 20 20

    - - ``//a[@href]``
      - turbohtml
      - lxml
      - speed-up
    - - per call (reparsed each time)
      - 0.6 µs
      - 4.1 µs
      - 6.8x
    - - precompiled, reused
      - 0.5 µs
      - 2.8 µs
      - 5.6x

.. testcode::

    from turbohtml import XPath

    links = XPath("//a[@href=$u]")
    doc = parse('<div><a href="/x">go</a><a href="/y">stay</a></div>')
    print([link.attrs["href"] for link in links(doc, u="/x")])

.. testoutput::

    ['/x']

**********
 Pitfalls
**********

- No ``text``/``tail``. A node's children are its text runs and elements interleaved; read :attr:`~turbohtml.Node.text`
  for the concatenation.
- lxml parses with libxml2, which is not WHATWG-conformant, so malformed input lands in a different tree than the one
  turbohtml (and a browser) builds.
- For a document that arrives in pieces, ``etree.iterparse`` is replaced by :class:`turbohtml.IncrementalParser`: feed
  ``str`` or ``bytes`` chunks with ``feed`` and call ``close`` for the finished :class:`~turbohtml.Document`. The parser
  never holds the whole source at once, so you can parse a stream larger than the source buffer you would otherwise
  materialize for :func:`turbohtml.parse`.
- The wider libxml2 toolchain is a deliberate clean-break scope cut: XSLT, DTD/RelaxNG/XML-Schema validation, and C14N
  have no turbohtml equivalent. XPath is at parity, not a gap: both are XPath 1.0 with EXSLT (libxml2 has no XPath
  2.0/XQuery either), so an lxml ``xpath()`` call ports directly.
