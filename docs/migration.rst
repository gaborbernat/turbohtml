########################
 Migrating to turbohtml
########################

turbohtml is a native replacement for the HTML libraries it benchmarks against, not a drop-in for any of them. It picks
one name per concept and a typed shape where those libraries spread the work across aliases, methods, and treebuilder
choices, so porting is a translation. This page maps each one to turbohtml, library by library; BeautifulSoup gets the
deepest treatment because it shares the most surface.

********************
 From BeautifulSoup
********************

Parsing returns a :class:`~turbohtml.Document` instead of a ``BeautifulSoup`` object, and there is no parser name to
pass - turbohtml is always the WHATWG algorithm:

.. code-block:: python

    # BeautifulSoup
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(markup, "html.parser")

.. code-block:: pycon

    >>> from turbohtml import parse
    >>> doc = parse("<p id=intro>Hello</p>")
    >>> doc.find("p").attrs["id"]
    'intro'

Bytes work too; pass the raw response and read the resolved encoding back from :attr:`Document.encoding
<turbohtml.Document.encoding>`:

.. code-block:: pycon

    >>> doc = parse(b'<meta charset="latin-1"><p>caf\xe9</p>')
    >>> doc.find("p").text
    'café'
    >>> doc.encoding  # the WHATWG label latin-1 resolves to
    'windows-1252'

The renames
===========

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - BeautifulSoup
      - turbohtml
    - - ``tag.name``
      - ``element.tag``
    - - ``tag["class"]``, ``tag.get("x")``, ``tag.has_attr("x")``
      - ``element.attrs["class"]``, ``element.attrs.get("x")``, ``"x" in element.attrs``
    - - ``tag.string``, ``tag.get_text()``
      - ``node.text``, ``node.strings``, ``node.stripped_strings``
    - - ``tag.parents``
      - ``node.ancestors``
    - - ``tag.contents``, ``list(tag.children)``
      - ``node.children``
    - - ``tag.next_elements``
      - ``node.following``
    - - ``tag.find_parent(...)``
      - ``node.find(..., axis=Axis.ANCESTORS)`` or ``node.closest(selector)``
    - - ``tag.find_next(...)``, ``tag.find_previous(...)``
      - ``node.find(..., axis=Axis.FOLLOWING)``, ``node.find(..., axis=Axis.PRECEDING)``
    - - ``tag.find_next_sibling(...)``, ``tag.find_previous_sibling(...)``
      - ``node.find(..., axis=Axis.NEXT_SIBLINGS)``, ``node.find(..., axis=Axis.PREVIOUS_SIBLINGS)``
    - - ``tag.find_all("a", recursive=False)``
      - ``element.find_all("a", axis=Axis.CHILDREN)``
    - - ``soup.select(".cls")``, ``soup.select_one(".cls")``
      - ``node.select(".cls")``, ``node.select_one(".cls")``
    - - ``tag.decompose()``, ``tag.extract()``, ``tag.unwrap()``, ``tag.wrap(...)``
      - ``node.decompose()``, ``node.extract()``, ``node.unwrap()``, ``node.wrap(...)``
    - - ``tag.insert_before(...)``, ``tag.insert_after(...)``, ``tag.replace_with(...)``
      - the same names on every :class:`~turbohtml.Node`
    - - ``soup.new_tag("div")``, ``soup.new_string("hi")``
      - ``Element("div")``, ``Text("hi")``
    - - ``tag.prettify()``
      - ``node.serialize(indent=2)``
    - - ``tag.smooth()``
      - ``element.normalize()``

Searching
=========

The ``find``/``find_all`` filter grammar covers what ``bs4`` spread across many methods. A keyword filter matches an
attribute; ``class_`` and ``attrs`` match the rest; ``axis`` replaces the directional finders and ``recursive=False``:

.. code-block:: pycon

    >>> from turbohtml import Axis
    >>> doc = parse('<ul><li class="x">a</li><li class="y">b</li></ul>')
    >>> [li.text for li in doc.find_all("li")]
    ['a', 'b']
    >>> doc.find("li", class_="y").text
    'b'
    >>> doc.find("ul").find_all("li", axis=Axis.CHILDREN, attrs={"class": "x"})
    [Element('li')]

``Axis`` reaches every direction a ``bs4`` directional finder did:

.. code-block:: pycon

    >>> deep = parse("<section><p><b>hi</b></p></section>").find("b")
    >>> deep.find("section", axis=Axis.ANCESTORS).tag
    'section'
    >>> deep.closest("section").tag
    'section'

Attributes and text
====================

``.attrs`` is the single access point - there is no ``tag["x"]`` shortcut, because ``node[i]`` indexes child nodes.
Multi-valued attributes (``class``, ``rel``, ...) read back as a ``list[str]``, and text is real child nodes (the
WHATWG DOM shape), so there is no ``.string`` shortcut and no ``lxml``-style ``text``/``tail`` split:

.. code-block:: pycon

    >>> a = parse('<a class="btn lg" href="/x">go</a>').find("a")
    >>> a.attrs["class"]
    ['btn', 'lg']
    >>> a[0]  # indexing reaches children, never attributes
    Text('go')
    >>> p = parse("<p>Hello <b>bold</b> world</p>").find("p")
    >>> p.text, list(p.stripped_strings)
    ('Hello bold world', ['Hello', 'bold', 'world'])

Output
======

The default serialization is WHATWG-conformant, so it differs from ``bs4``'s ``html`` formatter on named entities,
attribute order, and ``<br>`` versus ``<br/>``. Choose ``Formatter.NAMED_ENTITIES`` to approximate ``bs4``:

.. code-block:: pycon

    >>> from turbohtml import Formatter
    >>> node = parse("<p>café &amp; co</p>").find("p")
    >>> node.html
    '<p>café &amp; co</p>'
    >>> node.serialize(formatter=Formatter.NAMED_ENTITIES)
    '<p>caf&eacute; &amp; co</p>'

Pitfalls
========

-  ``node[i]`` indexes children; attributes are reached through ``.attrs``, never ``node["attr"]``.
-  Text is real child nodes, so there is no ``.string`` shortcut and no ``text``/``tail``; iterate the children.
-  Default output is WHATWG-conformant; pick ``Formatter.NAMED_ENTITIES`` to come close to ``bs4``'s ``html``
   formatter.
-  Equality is identity, not structural. Where ``bs4`` code leaned on ``==`` between trees, compare serializations
   (``a.html == b.html``) or walk the nodes.

***********
 From lxml
***********

:func:`turbohtml.parse` replaces ``lxml.html.document_fromstring`` and returns a :class:`~turbohtml.Document`;
:func:`turbohtml.parse_fragment` replaces ``lxml.html.fromstring`` for a fragment. The biggest change is the tree
shape: lxml stores text as an element's ``.text`` and ``.tail`` strings, while turbohtml models it as real child
:class:`~turbohtml.Text` nodes, so you iterate children instead of reading two string fields.

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - lxml
      - turbohtml
    - - ``el.tag``
      - ``el.tag`` (same)
    - - ``el.get("x")``, ``el.attrib``, ``el.set("x", "v")``
      - ``el.attrs.get("x")``, ``el.attrs``, ``el.attrs["x"] = "v"``
    - - ``el.text``, ``el.tail``
      - child :class:`~turbohtml.Text` nodes; iterate ``el.children``
    - - ``el.text_content()``
      - ``el.text``
    - - ``el.getparent()``, ``el.getnext()``, ``el.getprevious()``
      - ``el.parent``, ``el.next_sibling``, ``el.previous_sibling``
    - - ``list(el)``, ``el.iterdescendants()``, ``el.iterancestors()``
      - ``el.children``, ``el.descendants``, ``el.ancestors``
    - - ``el.findall(".//a")``, ``el.xpath("//a[@href]")``
      - ``el.find_all("a")``, ``el.find_all("a", attrs={"href": True})``
    - - ``el.cssselect("div a")``
      - ``el.select("div a")``
    - - ``lxml.html.Element("div")``, ``etree.SubElement(p, "div")``
      - ``Element("div")``, ``p.append(Element("div"))``
    - - ``el.drop_tag()``, ``el.drop_tree()``
      - ``el.unwrap()``, ``el.decompose()``
    - - ``lxml.html.tostring(el)``
      - ``el.html``

.. code-block:: pycon

    >>> doc = parse('<div><a href="/x">go</a></div>')
    >>> doc.find_all("a", attrs={"href": True})
    [Element('a')]
    >>> doc.select_one("div a").attrs["href"]
    '/x'

Pitfalls
========

-  No XPath. Use the ``find``/``find_all`` filter grammar (an ``axis``, ``attrs``, and string, regex, or callable
   filters) or CSS :meth:`~turbohtml.Node.select`.
-  No ``text``/``tail``. A node's children are its text runs and elements interleaved; read :attr:`~turbohtml.Node.text`
   for the concatenation.
-  lxml parses with libxml2, which is not WHATWG-conformant, so malformed input lands in a different tree than the one
   turbohtml (and a browser) builds.

*****************
 From selectolax
*****************

selectolax wraps the same lexbor engine turbohtml benchmarks against, so the speed is comparable; the move is mostly
API surface. selectolax searches with CSS only and exposes ``text()`` as a method, while turbohtml adds the
``find``/``find_all`` filter grammar and makes :attr:`~turbohtml.Node.text` a property.

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - selectolax
      - turbohtml
    - - ``LexborHTMLParser(html)``
      - ``turbohtml.parse(html)``
    - - ``parser.root``, ``parser.body``
      - ``doc.root``, ``doc.find("body")``
    - - ``node.css("a")``, ``node.css_first("a")``
      - ``node.select("a")``, ``node.select_one("a")``
    - - ``node.tag``
      - ``node.tag`` (same)
    - - ``node.attributes``
      - ``node.attrs``
    - - ``node.text()`` (a method)
      - ``node.text`` (a property), ``node.strings``, ``node.stripped_strings``
    - - ``node.html``, ``node.decompose()``, ``node.unwrap()``
      - the same names

.. code-block:: pycon

    >>> doc = parse("<ul><li>a</li><li>b</li></ul>")
    >>> [li.text for li in doc.select("li")]
    ['a', 'b']

Pitfalls
========

-  selectolax queries are CSS-only; turbohtml adds the ``find``/``find_all`` filter grammar with axes and regex or
   callable filters.
-  ``node.text`` is a property, not a method - drop the parentheses.
-  selectolax mutation is limited; turbohtml's edit surface (``append``, ``insert``, ``wrap``, ``unwrap``,
   ``replace_with``, and the rest) is full.

****************
 From html5lib
****************

html5lib runs the same WHATWG algorithm turbohtml does, so the *tree* it produces matches; what changes is that
html5lib hands you a generic tree you select with a treebuilder (an :mod:`xml.etree.ElementTree` element by default, or
DOM, or lxml), while turbohtml has one typed hierarchy with navigation, search, and serialization built in.

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - html5lib
      - turbohtml
    - - ``html5lib.parse(s)``
      - ``turbohtml.parse(s)``
    - - ``html5lib.parse(s, treebuilder="dom")``
      - one typed tree, no treebuilder choice
    - - ``html5lib.parseFragment(s, container="div")``
      - ``turbohtml.parse_fragment(s, "div")``
    - - the html5lib tokenizer
      - ``turbohtml.tokenize(s)``, ``turbohtml.Tokenizer``
    - - ``el.tag`` namespaced (``{http://www.w3.org/1999/xhtml}div``)
      - ``el.tag`` plus an :class:`~turbohtml.Namespace` on ``el.namespace``
    - - the treebuilder's own walk and ``el.attrib``
      - ``el.children``, ``el.find``/``el.select``, ``el.attrs``

.. code-block:: pycon

    >>> doc = parse("<table><tr><td>x")  # the same tree html5lib and a browser build
    >>> doc.find("td").text
    'x'

Pitfalls
========

-  html5lib gives you a foreign tree (ElementTree, DOM, or lxml) and you pick a treebuilder; turbohtml has one typed
   tree, so there is nothing to choose and the node types are sealed and pattern-matchable.
-  html5lib's ElementTree output namespaces names; turbohtml keeps ``tag`` plain and carries the namespace separately
   as :attr:`~turbohtml.Element.namespace`.

***************************
 From the standard library
***************************

:func:`turbohtml.escape` and :func:`turbohtml.unescape` reproduce :func:`python:html.escape` and
:func:`python:html.unescape` byte for byte, so they are a drop-in:

.. code-block:: pycon

    >>> import html
    >>> from turbohtml import escape, unescape
    >>> escape('<a href="x">') == html.escape('<a href="x">')
    True
    >>> unescape("caf&eacute; &#127881;") == html.unescape("caf&eacute; &#127881;")
    True

In place of subclassing :class:`python:html.parser.HTMLParser` with ``handle_starttag`` and ``handle_data`` callbacks,
take the token stream from :func:`turbohtml.tokenize` (or :meth:`turbohtml.Tokenizer.feed` for incremental input), or
skip tokens entirely and :func:`turbohtml.parse` straight to a tree. Unlike ``html.parser``, both are
WHATWG-conformant. The :doc:`how-to` guide has a worked port.
