######################
 From lxml-html-clean
######################

.. package-meta:: lxml_html_clean fedora-python/lxml_html_clean

`lxml-html-clean <https://github.com/fedora-python/lxml_html_clean>`_ is the ``Cleaner`` split out of
``lxml.html.clean``. It is a **blocklist**: you toggle off categories of dangerous content (``scripts``, ``javascript``,
``style``, ``comments``, ``embedded``, ``frames``, ``forms``, ``meta``, ...) and everything else survives, so a tag the
library has not heard of passes through.

***************
 Why turbohtml
***************

``turbohtml.clean`` takes the opposite, safer stance: it is an **allowlist**, so nothing survives unless a
:class:`~turbohtml.clean.Policy` names it, which is why the safety baseline holds against markup the author never
anticipated. It is fully type annotated and runs the filtering walk in C rather than over an lxml tree, leading the
blocklist cleaner by an order of magnitude:

.. bench-table::
    :file: bench/lxml-html-clean.json

*************
 The renames
*************

Porting inverts the model. Instead of switching dangerous things off, declare the small set you keep:

.. code-block:: python

    # lxml-html-clean: enumerate what to strip, keep the rest
    from lxml_html_clean import Cleaner

    Cleaner(scripts=True, javascript=True, comments=True, style=True, forms=True).clean_html(text)

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - `lxml-html-clean <https://lxml-html-clean.readthedocs.io/>`__
      - turbohtml
    - - ``Cleaner(...).clean_html(text)``
      - :func:`turbohtml.clean.sanitize` with a :class:`~turbohtml.clean.Policy`
    - - ``host_whitelist=``, ``allow_tags=``
      - ``Policy.tags`` and ``Policy.attribute_filter``
    - - ``kill_tags=`` (drop element with content)
      - ``Policy.remove_with_content``
    - - ``add_nofollow=``
      - ``Policy.add_link_rel``

.. testcode::

    from turbohtml.clean import sanitize, Policy

    print(
        sanitize(
            "<p>Hi<script>x()</script> <a href='javascript:1'>l</a></p>",
            Policy(tags=frozenset({"p", "a"}), attributes={"a": frozenset({"href"})}),
        )
    )

.. testoutput::

    <p>Hi&lt;script&gt;x()&lt;/script&gt; <a>l</a></p>

The ``javascript:`` URL is gone because ``http``/``https``/``mailto`` are the only schemes the policy admits, and the
``<script>`` is escaped rather than executed.

**********
 Pitfalls
**********

- turbohtml scrubs a kept ``style`` attribute against ``Policy.css_properties`` but drops ``<style>`` elements, where
  ``Cleaner`` scrubs their text too.
- ``Cleaner`` rewrites a disallowed scheme to an empty ``href`` where turbohtml drops the attribute outright.
