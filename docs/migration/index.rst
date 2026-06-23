########################
 Migrating to turbohtml
########################

turbohtml replaces the HTML libraries it benchmarks against. None is API-compatible, so porting is a translation:
turbohtml uses one name per concept and a typed shape where those libraries spread the work across aliases, methods, and
treebuilder choices. This page maps each library to turbohtml; `BeautifulSoup
<https://www.crummy.com/software/BeautifulSoup/>`_ gets the deepest treatment because it shares the most surface.

The guides are ordered by adoption, most to least monthly PyPI downloads, so the libraries you are most likely to port
from come first.

.. list-table::
    :header-rows: 1
    :widths: auto

    - - Library
      - Monthly downloads
    - - :doc:`pandas <pandas>`
      - .. image:: https://static.pepy.tech/badge/pandas/month
            :alt: pandas monthly downloads
            :target: https://pepy.tech/project/pandas
    - - :doc:`markupsafe <markupsafe>`
      - .. image:: https://static.pepy.tech/badge/markupsafe/month
            :alt: markupsafe monthly downloads
            :target: https://pepy.tech/project/markupsafe
    - - :doc:`beautifulsoup <beautifulsoup>`
      - .. image:: https://static.pepy.tech/badge/beautifulsoup4/month
            :alt: beautifulsoup4 monthly downloads
            :target: https://pepy.tech/project/beautifulsoup4
    - - :doc:`lxml <lxml>`
      - .. image:: https://static.pepy.tech/badge/lxml/month
            :alt: lxml monthly downloads
            :target: https://pepy.tech/project/lxml
    - - :doc:`linkify-it-py <linkify-it-py>`
      - .. image:: https://static.pepy.tech/badge/linkify-it-py/month
            :alt: linkify-it-py monthly downloads
            :target: https://pepy.tech/project/linkify-it-py
    - - :doc:`bleach <bleach>`
      - .. image:: https://static.pepy.tech/badge/bleach/month
            :alt: bleach monthly downloads
            :target: https://pepy.tech/project/bleach
    - - :doc:`markdownify <markdownify>`
      - .. image:: https://static.pepy.tech/badge/markdownify/month
            :alt: markdownify monthly downloads
            :target: https://pepy.tech/project/markdownify
    - - :doc:`nh3 <nh3>`
      - .. image:: https://static.pepy.tech/badge/nh3/month
            :alt: nh3 monthly downloads
            :target: https://pepy.tech/project/nh3
    - - :doc:`html5lib <html5lib>`
      - .. image:: https://static.pepy.tech/badge/html5lib/month
            :alt: html5lib monthly downloads
            :target: https://pepy.tech/project/html5lib
    - - :doc:`html2text <html2text>`
      - .. image:: https://static.pepy.tech/badge/html2text/month
            :alt: html2text monthly downloads
            :target: https://pepy.tech/project/html2text
    - - :doc:`lxml-html-clean <lxml-html-clean>`
      - .. image:: https://static.pepy.tech/badge/lxml_html_clean/month
            :alt: lxml-html-clean monthly downloads
            :target: https://pepy.tech/project/lxml_html_clean
    - - :doc:`w3lib <w3lib>`
      - .. image:: https://static.pepy.tech/badge/w3lib/month
            :alt: w3lib monthly downloads
            :target: https://pepy.tech/project/w3lib
    - - :doc:`trafilatura <trafilatura>`
      - .. image:: https://static.pepy.tech/badge/trafilatura/month
            :alt: trafilatura monthly downloads
            :target: https://pepy.tech/project/trafilatura
    - - :doc:`selectolax <selectolax>`
      - .. image:: https://static.pepy.tech/badge/selectolax/month
            :alt: selectolax monthly downloads
            :target: https://pepy.tech/project/selectolax
    - - :doc:`parsel <parsel>`
      - .. image:: https://static.pepy.tech/badge/parsel/month
            :alt: parsel monthly downloads
            :target: https://pepy.tech/project/parsel
    - - :doc:`pyquery <pyquery>`
      - .. image:: https://static.pepy.tech/badge/pyquery/month
            :alt: pyquery monthly downloads
            :target: https://pepy.tech/project/pyquery
    - - :doc:`dominate <dominate>`
      - .. image:: https://static.pepy.tech/badge/dominate/month
            :alt: dominate monthly downloads
            :target: https://pepy.tech/project/dominate
    - - :doc:`inscriptis <inscriptis>`
      - .. image:: https://static.pepy.tech/badge/inscriptis/month
            :alt: inscriptis monthly downloads
            :target: https://pepy.tech/project/inscriptis
    - - :doc:`readability-lxml <readability-lxml>`
      - .. image:: https://static.pepy.tech/badge/readability-lxml/month
            :alt: readability-lxml monthly downloads
            :target: https://pepy.tech/project/readability-lxml
    - - :doc:`html-text <html-text>`
      - .. image:: https://static.pepy.tech/badge/html-text/month
            :alt: html-text monthly downloads
            :target: https://pepy.tech/project/html-text
    - - :doc:`resiliparse <resiliparse>`
      - .. image:: https://static.pepy.tech/badge/resiliparse/month
            :alt: resiliparse monthly downloads
            :target: https://pepy.tech/project/resiliparse
    - - :doc:`newspaper3k <newspaper3k>`
      - .. image:: https://static.pepy.tech/badge/newspaper3k/month
            :alt: newspaper3k monthly downloads
            :target: https://pepy.tech/project/newspaper3k
    - - :doc:`html-sanitizer <html-sanitizer>`
      - .. image:: https://static.pepy.tech/badge/html-sanitizer/month
            :alt: html-sanitizer monthly downloads
            :target: https://pepy.tech/project/html-sanitizer
    - - :doc:`extruct <extruct>`
      - .. image:: https://static.pepy.tech/badge/extruct/month
            :alt: extruct monthly downloads
            :target: https://pepy.tech/project/extruct
    - - :doc:`mechanicalsoup <mechanicalsoup>`
      - .. image:: https://static.pepy.tech/badge/MechanicalSoup/month
            :alt: MechanicalSoup monthly downloads
            :target: https://pepy.tech/project/MechanicalSoup
    - - :doc:`html5-parser <html5-parser>`
      - .. image:: https://static.pepy.tech/badge/html5-parser/month
            :alt: html5-parser monthly downloads
            :target: https://pepy.tech/project/html5-parser
    - - :doc:`stdlib <stdlib>`
      - Bundled with Python

.. toctree::
    :hidden:
    :maxdepth: 1

    pandas
    markupsafe
    beautifulsoup
    lxml
    linkify-it-py
    bleach
    markdownify
    nh3
    html5lib
    html2text
    lxml-html-clean
    w3lib
    trafilatura
    selectolax
    parsel
    dominate
    pyquery
    inscriptis
    readability-lxml
    html-text
    resiliparse
    newspaper3k
    html-sanitizer
    extruct
    mechanicalsoup
    html5-parser
    stdlib
