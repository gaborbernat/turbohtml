###############
 From html5lib
###############

.. package-meta:: html5lib html5lib/html5lib-python

`html5lib <https://html5lib.readthedocs.io>`_ is the reference pure-Python implementation of the WHATWG parsing
algorithm: it tokenizes and builds a tree that you select through a treebuilder (an :mod:`xml.etree.ElementTree` element
by default, or DOM, or lxml), and it is the conformance baseline other parsers are checked against.

***************
 Why turbohtml
***************

turbohtml runs the same WHATWG algorithm, so the *tree* matches, but it produces one typed hierarchy with navigation,
search, and serialization built in instead of a foreign tree behind a treebuilder choice. The algorithm runs in C, so
parsing, tokenizing, and fragment parsing run 25 to 70 times faster than the pure-Python implementation
(:func:`turbohtml.parse_fragment` parses an ``innerHTML``-style snippet in its container context, the same WHATWG
fragment algorithm html5lib's :func:`~html5lib.html5parser.parseFragment` runs):

.. bench-table::
    :file: bench/html5lib.json

*************
 The renames
*************

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - `html5lib <https://html5lib.readthedocs.io/>`__
      - turbohtml
    - - :func:`html5lib.parse() <html5lib.html5parser.parse>`
      - :func:`turbohtml.parse`
    - - ``html5lib.parse(s, treebuilder="dom")``
      - one typed tree, no treebuilder choice
    - - :func:`html5lib.parseFragment() <html5lib.html5parser.parseFragment>`
      - :func:`turbohtml.parse_fragment`
    - - the html5lib tokenizer
      - :func:`turbohtml.tokenize`, :class:`turbohtml.Tokenizer`
    - - ``el.tag`` namespaced (``{http://www.w3.org/1999/xhtml}div``)
      - :attr:`~turbohtml.Element.tag` plus :class:`~turbohtml.Namespace` on :attr:`~turbohtml.Element.namespace`
    - - the treebuilder's own walk and ``el.attrib``
      - :attr:`~turbohtml.Node.children`, :meth:`~turbohtml.Node.find` / :meth:`~turbohtml.Node.select`,
        :attr:`~turbohtml.Element.attrs`

.. testcode::

    doc = parse("<table><tr><td>x")  # the same tree html5lib and a browser build
    print(doc.find("td").text)

.. testoutput::

    x

**********
 Pitfalls
**********

- html5lib gives you a foreign tree (ElementTree, DOM, or lxml) and you pick a treebuilder; turbohtml has one typed
  tree, so there is nothing to choose and the node types are sealed and pattern-matchable.
- html5lib's ElementTree output namespaces names; turbohtml keeps ``tag`` plain and carries the namespace separately as
  :attr:`~turbohtml.Element.namespace`.
