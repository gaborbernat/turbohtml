#########################
 Extract structured data
#########################

****************************************
 Pull every embedded format in one call
****************************************

Scrapers want the JSON-LD, Microdata, and OpenGraph/Twitter metadata a page embeds, the job of ``extruct`` or
``metadata_parser``. :meth:`~turbohtml.Document.structured_data` pulls every supported format in one walk:

.. testcode::

    doc = turbohtml.parse(
        '<head><meta property="og:title" content="Widgets"></head>'
        '<body><script type="application/ld+json">{"@type": "Product", "name": "Widget"}</script>'
        '<div itemscope itemtype="https://schema.org/Offer"><span itemprop="price">9.99</span></div></body>'
    )
    data = doc.structured_data()
    print(data.json_ld)
    print(data.opengraph)
    item = data.microdata[0]
    print(item.type, item.properties)

.. testoutput::

    [{'@type': 'Product', 'name': 'Widget'}]
    {'og:title': 'Widgets'}
    https://schema.org/Offer {'price': ['9.99']}

:meth:`~turbohtml.Document.structured_data` returns a :class:`~turbohtml.StructuredData` record whose fields you read by
attribute. The per-format helpers :meth:`~turbohtml.Document.json_ld`, :meth:`~turbohtml.Document.opengraph`, and
:meth:`~turbohtml.Document.microdata` return just one format each, the last as a list of
:class:`~turbohtml.MicrodataItem`. JSON-LD blocks are parsed with the standard library :mod:`json` and a block that is
not valid JSON is skipped; the :attr:`~turbohtml.StructuredData.microformats` and :attr:`~turbohtml.StructuredData.rdfa`
fields are reserved for a later phase and are empty lists for now.
