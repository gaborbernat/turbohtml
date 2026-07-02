#################
 From markupsafe
#################

.. package-meta:: markupsafe pallets/markupsafe

`markupsafe <https://markupsafe.palletsprojects.com>`_ is the safe-string library behind `Jinja2
<https://jinja.palletsprojects.com>`_, `WTForms <https://wtforms.readthedocs.io>`_, and `Werkzeug
<https://werkzeug.palletsprojects.com>`_: it provides a ``Markup`` string subclass and an ``escape`` function so a
template engine can interpolate untrusted values into HTML without escaping safe markup twice.

***************
 Why turbohtml
***************

``turbohtml.migration.markupsafe`` is a drop-in for markupsafe's public surface, fully type annotated, with the escape
and every ``Markup`` operation implemented in C. It also keeps one name per concept: :meth:`~turbohtml.escape` and the
tokenizer back the same primitives the rest of the library uses. The escape runs two to three times faster than
markupsafe's own C escape on the small, mostly-clean strings a template engine interpolates under autoescape, and the
other ``Markup`` operations stay ahead too -- ``striptags`` and ``unescape`` run on turbohtml's tokenizer and HTML5
reference resolution rather than markupsafe's regex scan, and the composing operations (``format``, ``join``) escape
each untrusted operand through the same C ``escape``:

.. bench-table::
    :file: bench/markupsafe.json

*************
 The renames
*************

A Jinja2, WTForms, or Werkzeug project changes only the import line:

.. code-block:: python

    # markupsafe
    from markupsafe import Markup, escape, escape_silent, soft_str, EscapeFormatter

    # turbohtml
    from turbohtml.migration.markupsafe import (
        Markup,
        escape,
        escape_silent,
        soft_str,
        EscapeFormatter,
    )

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - `markupsafe <https://markupsafe.palletsprojects.com/>`__
      - turbohtml
    - - :class:`markupsafe.Markup`
      - :class:`~turbohtml.migration.markupsafe.Markup`
    - - :func:`markupsafe.escape`
      - :func:`~turbohtml.migration.markupsafe.escape`
    - - :func:`markupsafe.escape_silent`
      - :func:`~turbohtml.migration.markupsafe.escape_silent`
    - - :func:`markupsafe.soft_str`
      - :func:`~turbohtml.migration.markupsafe.soft_str`
    - - ``EscapeFormatter``
      - :class:`~turbohtml.migration.markupsafe.EscapeFormatter`
    - - :meth:`markupsafe.Markup.striptags`
      - :meth:`~turbohtml.migration.markupsafe.Markup.striptags`
    - - :meth:`markupsafe.Markup.unescape`
      - :meth:`~turbohtml.migration.markupsafe.Markup.unescape`
    - - ``Markup.format``, ``Markup.join``
      - :meth:`~turbohtml.migration.markupsafe.Markup.format`, :meth:`~turbohtml.migration.markupsafe.Markup.join`

``escape`` returns a :class:`~turbohtml.migration.markupsafe.Markup` with the same numeric quote references markupsafe
emits, honors the ``__html__`` protocol, and leaves an existing ``Markup`` untouched. ``Markup`` overrides the full
:class:`str` method surface, so a value that flows through a template filter such as ``upper`` or ``replace`` stays a
``Markup`` and autoescaping does not escape it a second time. The operations that combine text (``+``, ``%``,
:meth:`~turbohtml.migration.markupsafe.Markup.format`, :meth:`~turbohtml.migration.markupsafe.Markup.join`, ``replace``,
...) escape their untrusted operands:

.. testcode::

    from turbohtml.migration.markupsafe import Markup, escape, escape_silent

    print(escape('<a href="x">Tom & Jerry</a>'))
    print(Markup("<b>{}</b>").format("<i>"))
    print(Markup("<b>safe</b>").upper())  # str methods keep the Markup, so it is not re-escaped
    print(escape_silent(None) == Markup(""))

.. testoutput::

    &lt;a href=&#34;x&#34;&gt;Tom &amp; Jerry&lt;/a&gt;
    <b>&lt;i&gt;</b>
    <B>SAFE</B>
    True

Two methods are upgrades rather than reimplementations: :meth:`~turbohtml.migration.markupsafe.Markup.striptags` and
:meth:`~turbohtml.migration.markupsafe.Markup.unescape` run on turbohtml's tokenizer and HTML5 reference resolution, so
they are faster and resolve references markupsafe's regex-based stripping can miss.

**********
 Pitfalls
**********

- The ``soft_unicode`` alias that markupsafe 3.0 removed is absent here too; use
  :func:`~turbohtml.migration.markupsafe.soft_str`.
- turbohtml does not register itself as ``markupsafe``, so adoption stays an explicit per-project import rather than a
  transparent replacement of the installed package.
