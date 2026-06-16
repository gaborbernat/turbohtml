####################################
 Migrate from BeautifulSoup
####################################

turbohtml is a native replacement for BeautifulSoup, not a drop-in one. It picks one name per concept and a typed
shape where ``bs4`` carries aliases and overloads, so porting is a translation, not a find-and-replace. This page maps
each ``bs4`` idiom to its turbohtml equivalent and calls out the behavior differences you will hit.

***************
 The one rename
***************

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

*******************
 Translation table
*******************

.. list-table::
    :header-rows: 1
    :widths: 50 50

    -  -  BeautifulSoup
       -  turbohtml
    -  -  ``tag.name``
       -  ``element.tag``
    -  -  ``tag["class"]``, ``tag.get("x")``, ``tag.has_attr("x")``
       -  ``element.attrs["class"]``, ``element.attrs.get("x")``, ``"x" in element.attrs``
    -  -  ``tag.string``, ``tag.get_text()``
       -  ``node.text``, ``node.strings``, ``node.stripped_strings``
    -  -  ``tag.parents``
       -  ``node.ancestors``
    -  -  ``tag.contents``, ``list(tag.children)``
       -  ``node.children``
    -  -  ``tag.next_elements``
       -  ``node.following``
    -  -  ``tag.find_parent(...)``
       -  ``node.find(..., axis=Axis.ANCESTORS)`` or ``node.closest(selector)``
    -  -  ``tag.find_next(...)``, ``tag.find_previous(...)``
       -  ``node.find(..., axis=Axis.FOLLOWING)``, ``node.find(..., axis=Axis.PRECEDING)``
    -  -  ``tag.find_next_sibling(...)``, ``tag.find_previous_sibling(...)``
       -  ``node.find(..., axis=Axis.NEXT_SIBLINGS)``, ``node.find(..., axis=Axis.PREVIOUS_SIBLINGS)``
    -  -  ``tag.find_all("a", recursive=False)``
       -  ``element.find_all("a", axis=Axis.CHILDREN)``
    -  -  ``soup.select(".cls")``, ``soup.select_one(".cls")``
       -  ``node.select(".cls")``, ``node.select_one(".cls")``
    -  -  ``tag.decompose()``, ``tag.extract()``, ``tag.unwrap()``, ``tag.wrap(...)``
       -  ``node.decompose()``, ``node.extract()``, ``node.unwrap()``, ``node.wrap(...)``
    -  -  ``tag.insert_before(...)``, ``tag.insert_after(...)``, ``tag.replace_with(...)``
       -  the same names on every :class:`~turbohtml.Node`
    -  -  ``soup.new_tag("div")``, ``soup.new_string("hi")``
       -  ``Element("div")``, ``Text("hi")``
    -  -  ``tag.prettify()``
       -  ``node.serialize(indent=2)``
    -  -  ``tag.smooth()``
       -  ``element.normalize()``

****************
 Searching
****************

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

****************
 Attributes
****************

``.attrs`` is the single access point - there is no ``tag["x"]`` shortcut, because ``node[i]`` indexes child nodes.
Multi-valued attributes (``class``, ``rel``, ...) read back as a ``list[str]``:

.. code-block:: pycon

    >>> a = parse('<a class="btn lg" href="/x">go</a>').find("a")
    >>> a.attrs["class"]
    ['btn', 'lg']
    >>> a.attrs.get("href")
    '/x'
    >>> "href" in a.attrs
    True
    >>> a[0]  # indexing reaches children, never attributes  # doctest: +ELLIPSIS
    Text('go')

****************
 Text
****************

turbohtml models text as real child nodes (the WHATWG DOM shape), so there is no ``.string`` single-child shortcut and
no ``lxml``-style ``text``/``tail`` split. Read text with :attr:`~turbohtml.Node.text`, or iterate
:attr:`~turbohtml.Node.strings`:

.. code-block:: pycon

    >>> p = parse("<p>Hello <b>bold</b> world</p>").find("p")
    >>> p.text
    'Hello bold world'
    >>> list(p.stripped_strings)
    ['Hello', 'bold', 'world']

**********************
 Building and editing
**********************

Construct nodes directly and assemble them; a node already in a tree moves, a node from another tree is adopted by
copy:

.. code-block:: pycon

    >>> from turbohtml import Element, Text
    >>> card = Element("div", {"class": "card"})
    >>> card.append(Element("h2"))
    >>> card.children[0].text = "Title"
    >>> card.html
    '<div class="card"><h2>Title</h2></div>'

The structural edits keep their ``bs4`` names:

.. code-block:: pycon

    >>> doc = parse("<p><b>x</b> y</p>")
    >>> doc.find("b").unwrap()  # doctest: +ELLIPSIS
    Element('b')
    >>> doc.find("p").html
    '<p>x y</p>'

****************
 Output
****************

The default serialization is WHATWG-conformant, so it differs from ``bs4``'s ``html`` formatter on named entities,
attribute order, and ``<br>`` versus ``<br/>``. Choose ``Formatter.NAMED_ENTITIES`` to approximate ``bs4``:

.. code-block:: pycon

    >>> from turbohtml import Formatter
    >>> node = parse("<p>café &amp; co</p>").find("p")
    >>> node.html
    '<p>café &amp; co</p>'
    >>> node.serialize(formatter=Formatter.NAMED_ENTITIES)
    '<p>caf&eacute; &amp; co</p>'

*****************
 Pitfalls
*****************

-  ``node[i]`` indexes children; attributes are reached through ``.attrs``, never ``node["attr"]``.
-  Text is real child nodes, so there is no ``.string`` shortcut and no ``text``/``tail``; iterate the children.
-  Default output is WHATWG-conformant; pick ``Formatter.NAMED_ENTITIES`` to come close to ``bs4``'s ``html``
   formatter.
-  Equality is identity, not structural. Where ``bs4`` code leaned on ``==`` between trees, compare serializations
   (``a.html == b.html``) or walk the nodes.
