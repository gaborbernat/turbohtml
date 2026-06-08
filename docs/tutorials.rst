###########
 Tutorials
###########

*****************
 Getting started
*****************

This tutorial walks you from an empty environment to escaping and unescaping your first HTML.

Install turbohtml from PyPI:

.. code-block:: console

    $ pip install turbohtml

Open a Python prompt and escape some text for safe inclusion in an HTML page:

.. code-block:: pycon

    >>> import turbohtml
    >>> turbohtml.escape("5 > 3 & 2 < 4")
    '5 &gt; 3 &amp; 2 &lt; 4'

By default the quotation marks are escaped too, which is what you want inside an attribute value:

.. code-block:: pycon

    >>> turbohtml.escape("name=\"O'Brien\"")
    'name=&quot;O&#x27;Brien&quot;'

Now go the other way and turn HTML character references back into text:

.. code-block:: pycon

    >>> turbohtml.unescape("Tom &amp; Jerry &mdash; caf&eacute;")
    'Tom & Jerry — café'

That is the whole core API. From here, head to the :doc:`how-to` guides for task-focused recipes, or the
:doc:`reference` for the exact signatures.
