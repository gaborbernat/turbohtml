###########
 Serialize
###########

Move escaping, Markdown, and text conversion to turbohtml.

For HTML fragments without a wrapper, use ``serialize(inner=True)`` or ``encode(inner=True)``. Use
``serialize_iter(inner=True)`` to stream compact or indented child output, and ``inner_xml`` for XML fragments. See
:doc:`/how-to/transforming-trees` for cleanup before serialization. These APIs emit markup; the conversion guides below
cover Markdown and plain-text output.

.. toctree::
    :maxdepth: 1

    markupsafe
    markdownify
    html2text
    inscriptis
    html-text
