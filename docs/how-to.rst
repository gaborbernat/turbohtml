How-to guides
=============

Escape untrusted text for HTML output
--------------------------------------

When you interpolate user-supplied text into HTML, escape it first so it cannot
break out of its context:

.. code-block:: pycon

    >>> import turbohtml
    >>> comment = '<script>alert("xss")</script>'
    >>> f"<p>{turbohtml.escape(comment)}</p>"
    '<p>&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;</p>'

Escape for a text node without touching quotes
-----------------------------------------------

Inside element text (not an attribute) the quote characters are safe, so pass
``quote=False`` to leave them untouched and keep the output smaller:

.. code-block:: pycon

    >>> turbohtml.escape('He said "hi" & left', quote=False)
    'He said "hi" &amp; left'

Decode HTML character references
--------------------------------

Convert named and numeric references from scraped or stored HTML back into
text:

.. code-block:: pycon

    >>> turbohtml.unescape("&pound;10 &mdash; &#127881;")
    '£10 — 🎉'

Unescaping follows the HTML5 rules, including longest-match for references that
omit the trailing semicolon:

.. code-block:: pycon

    >>> turbohtml.unescape("&notit;")
    '¬it;'
