##########
 From nh3
##########

.. package-meta:: nh3 messense/nh3

`nh3 <https://nh3.readthedocs.io>`_ is the Python binding for the Rust `ammonia
<https://github.com/rust-ammonia/ammonia>`_ HTML sanitizer, a common bleach refugee target. It is an allowlist
sanitizer, but it declined bleach feature parity: no escape-instead-of-strip mode, no attribute-rewriting callable, and
no linkifier.

***************
 Why turbohtml
***************

``turbohtml.clean`` stays in the same performance tier as the Rust binding while restoring the features nh3 dropped: an
escape mode, a value-rewriting ``attribute_filter``, and a companion linkifier, all fully type annotated behind a frozen
:class:`~turbohtml.clean.Policy`. It also leads nh3 on the benchmark:

.. bench-table::
    :file: bench/nh3.json

*************
 The renames
*************

.. code-block:: python

    # nh3
    import nh3

    nh3.clean(text, tags={"a"}, attributes={"a": {"href"}})

    # turbohtml
    from turbohtml.clean import sanitize, Policy

    sanitize(text, Policy(tags=frozenset({"a"}), attributes={"a": frozenset({"href"})}))

.. list-table::
    :header-rows: 1
    :widths: 50 50

    - - `nh3 <https://nh3.readthedocs.io/>`__
      - turbohtml
    - - ``nh3.clean(text, ...)``
      - :func:`turbohtml.clean.sanitize` with a :class:`~turbohtml.clean.Policy`
    - - ``tags=``, ``attributes=``
      - ``Policy.tags``, ``Policy.attributes``
    - - ``link_rel=``
      - ``Policy.add_link_rel``
    - - ``url_schemes=``
      - ``Policy.url_schemes``
    - - ``attribute_filter=``
      - ``Policy.attribute_filter`` (may rewrite a value, not only drop it)
    - - ``set_tag_attribute_values=``
      - ``Policy.set_attributes``
    - - (drops disallowed tags)
      - :class:`~turbohtml.clean.OnDisallowed` (``ESCAPE`` by default; ``STRIP`` / ``REMOVE`` for nh3-style dropping)
