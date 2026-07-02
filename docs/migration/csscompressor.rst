####################
 From csscompressor
####################

.. package-meta:: csscompressor sprymix/csscompressor

`csscompressor <https://github.com/sprymix/csscompressor>`_ is a pure-Python port of the YUI CSS compressor. Like
turbohtml it *rewrites* values -- colors to hex, redundant zeros and units dropped -- so it is in the same minifier
class, not a whitespace-only stripper. ``csscompressor.compress`` maps to :func:`turbohtml.clean.minify_css`, which
produces a smaller result and runs in C rather than chained regular expressions.

***************
 Why turbohtml
***************

turbohtml's output is smaller on every framework, including the custom-property-heavy ``bulma.css``, and its C engine is
40x to 155x faster -- csscompressor's regex passes turn quadratic on a large stylesheet, where turbohtml stays linear.
csscompressor also rewrites whitespace inside custom-property values, which `CSS Variables 1 §2
<https://www.w3.org/TR/css-variables-1/#defining-variables>`_ keeps as the literal token stream that ``var()`` splices
verbatim, so its output is not guaranteed to parse to the same cascade. Each ratio is against turbohtml:

.. bench-table::
    :file: bench/csscompressor.json

turbohtml also folds constant ``calc()``, merges box longhands into shorthands, and combines adjacent equal-bodied
rules, none of which csscompressor attempts, so the size gap widens on framework CSS that leans on those forms.

************************
 csscompressor.compress
************************

The import and the call name are the only change:

.. code-block:: python

    # csscompressor
    from csscompressor import compress

    # turbohtml
    from turbohtml.clean import minify_css

.. testcode::

    from turbohtml.clean import minify_css

    print(minify_css("a{ color: rgb(255, 0, 0); width: calc(2px + 3px) }"))

.. testoutput::

    a{color:red;width:5px}

Pitfalls
========

- csscompressor's ``max_linelen`` argument, which wraps the output every *N* columns, has no turbohtml equivalent:
  turbohtml emits a single line, which is the right shape once the bytes are gzipped on the wire.
- turbohtml takes no options at all; every rewrite it applies is value-safe, so there is nothing to configure.
