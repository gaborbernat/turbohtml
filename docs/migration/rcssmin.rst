##############
 From rcssmin
##############

.. package-meta:: rcssmin ndparker/rcssmin

`rcssmin <https://github.com/ndparker/rcssmin>`_ is the most-used CSS minifier on PyPI, a fast C extension that is
deliberately *non-destructive*: it strips comments and collapses whitespace and rewrites nothing else, so ``#ffffff``
and ``0px`` survive untouched. ``rcssmin.cssmin`` maps to :func:`turbohtml.clean.minify_css`, which goes further --
every value-safe rewrite as well -- so the result is smaller while still parsing to the same cascade.

***************
 Why turbohtml
***************

turbohtml rewrites each value to its shortest equivalent form -- colors to their shortest hex or name, redundant zeros
and units dropped, constant ``calc()`` folded, longhands merged into shorthands, equal rules combined -- where rcssmin
leaves values verbatim. turbohtml's output is smaller on every framework except the custom-property-heavy ``bulma.css``,
where rcssmin ends 0.1% ahead only by rewriting whitespace inside custom-property values. That rewrite is not
value-safe: `CSS Variables 1 §2 <https://www.w3.org/TR/css-variables-1/#defining-variables>`_ keeps a custom property's
value as its literal token stream, ``var()`` splices it verbatim and ``getPropertyValue()`` reads it back byte-exact, so
a collapsed space is observable wherever the value is substituted or compared. rcssmin's whitespace-only pass is faster
because it does strictly less work. Each ratio is against turbohtml:

.. bench-table::
    :file: bench/rcssmin.json

Both round-trip safely -- the output parses to the same cascade -- and both are idempotent. turbohtml is still far
faster than every *other* value-rewriting minifier, which are pure-Python and turn quadratic on a large stylesheet.

****************
 rcssmin.cssmin
****************

The import and the call name are the only change:

.. code-block:: python

    # rcssmin
    from rcssmin import cssmin

    # turbohtml
    from turbohtml.clean import minify_css

.. testcode::

    from turbohtml.clean import minify_css

    print(minify_css("a {\n  color: #ffffff;\n  margin: 0px 0px;\n}"))

.. testoutput::

    a{color:#fff;margin:0}

For the value of an HTML ``style`` attribute -- a bare declaration list with no selector or braces -- use
:func:`turbohtml.clean.minify_css_inline` instead:

.. testcode::

    from turbohtml.clean import minify_css_inline

    print(minify_css_inline("color: #ff0000 ; margin: 0.50px"))

.. testoutput::

    color:red;margin:.5px

Pitfalls
========

- turbohtml has no options: every transform it applies is value-safe, so there is nothing to turn off for correctness.
  rcssmin's ``keep_bang_comments`` flag has no turbohtml equivalent because turbohtml always keeps ``/*! ... */``
  license comments and always drops the rest.
- rcssmin is faster, because it only strips whitespace. Reach for it when a larger result is acceptable and raw speed
  matters more than size; reach for turbohtml when you want the smallest round-trip-safe output.
