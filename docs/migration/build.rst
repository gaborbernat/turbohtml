#######
 Build
#######

Move HTML-builder code to turbohtml.

A constructed turbohtml tree accepts the same cleanup stages as a parsed tree. Use ``transform_node`` before export and
``serialize(inner=True)`` for children without a wrapper. Retain the result if a stage returns a copied root. See
:doc:`/how-to/transforming-trees` for custom callables and ownership.

.. toctree::
    :maxdepth: 1

    dominate
    yattag
    htbuilder
    htpy
    airium
    markyp
    fast-html
    simple-html
    hyperpython
