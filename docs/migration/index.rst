########################
 Migrating to turbohtml
########################

turbohtml replaces the HTML libraries it benchmarks against. None is API-compatible, so porting is a translation:
turbohtml uses one name per concept and a typed shape where those libraries spread the work across aliases, methods, and
treebuilder choices. This page maps each library to turbohtml; `BeautifulSoup
<https://www.crummy.com/software/BeautifulSoup/>`_ gets the deepest treatment because it shares the most surface.

The guides are ordered by adoption, most to least monthly PyPI downloads, so the libraries you are most likely to port
from come first; the all-time totals and each library's documentation sit alongside for context.

.. list-table::
    :header-rows: 1
    :widths: auto

    - - #
      - Library
      - Docs
      - Monthly downloads
      - Total downloads
    - - 1
      - :doc:`pandas <pandas>`
      - `docs <https://pandas.pydata.org/docs/>`__
      - .. image:: https://static.pepy.tech/badge/pandas/month
            :alt: pandas monthly downloads
            :target: https://pepy.tech/project/pandas
      - .. image:: https://static.pepy.tech/badge/pandas
            :alt: pandas total downloads
            :target: https://pepy.tech/project/pandas
    - - 2
      - :doc:`markupsafe <markupsafe>`
      - `docs <https://markupsafe.palletsprojects.com/>`__
      - .. image:: https://static.pepy.tech/badge/markupsafe/month
            :alt: markupsafe monthly downloads
            :target: https://pepy.tech/project/markupsafe
      - .. image:: https://static.pepy.tech/badge/markupsafe
            :alt: markupsafe total downloads
            :target: https://pepy.tech/project/markupsafe
    - - 3
      - :doc:`beautifulsoup <beautifulsoup>`
      - `docs <https://www.crummy.com/software/BeautifulSoup/bs4/doc/>`__
      - .. image:: https://static.pepy.tech/badge/beautifulsoup4/month
            :alt: beautifulsoup4 monthly downloads
            :target: https://pepy.tech/project/beautifulsoup4
      - .. image:: https://static.pepy.tech/badge/beautifulsoup4
            :alt: beautifulsoup4 total downloads
            :target: https://pepy.tech/project/beautifulsoup4
    - - 4
      - :doc:`lxml <lxml>`
      - `docs <https://lxml.de/>`__
      - .. image:: https://static.pepy.tech/badge/lxml/month
            :alt: lxml monthly downloads
            :target: https://pepy.tech/project/lxml
      - .. image:: https://static.pepy.tech/badge/lxml
            :alt: lxml total downloads
            :target: https://pepy.tech/project/lxml
    - - 5
      - :doc:`linkify-it-py <linkify-it-py>`
      - `docs <https://github.com/tsutsu3/linkify-it-py>`__
      - .. image:: https://static.pepy.tech/badge/linkify-it-py/month
            :alt: linkify-it-py monthly downloads
            :target: https://pepy.tech/project/linkify-it-py
      - .. image:: https://static.pepy.tech/badge/linkify-it-py
            :alt: linkify-it-py total downloads
            :target: https://pepy.tech/project/linkify-it-py
    - - 6
      - :doc:`bleach <bleach>`
      - `docs <https://bleach.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/bleach/month
            :alt: bleach monthly downloads
            :target: https://pepy.tech/project/bleach
      - .. image:: https://static.pepy.tech/badge/bleach
            :alt: bleach total downloads
            :target: https://pepy.tech/project/bleach
    - - 7
      - :doc:`markdownify <markdownify>`
      - `docs <https://github.com/matthewwithanm/python-markdownify>`__
      - .. image:: https://static.pepy.tech/badge/markdownify/month
            :alt: markdownify monthly downloads
            :target: https://pepy.tech/project/markdownify
      - .. image:: https://static.pepy.tech/badge/markdownify
            :alt: markdownify total downloads
            :target: https://pepy.tech/project/markdownify
    - - 8
      - :doc:`nh3 <nh3>`
      - `docs <https://nh3.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/nh3/month
            :alt: nh3 monthly downloads
            :target: https://pepy.tech/project/nh3
      - .. image:: https://static.pepy.tech/badge/nh3
            :alt: nh3 total downloads
            :target: https://pepy.tech/project/nh3
    - - 9
      - :doc:`html5lib <html5lib>`
      - `docs <https://html5lib.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/html5lib/month
            :alt: html5lib monthly downloads
            :target: https://pepy.tech/project/html5lib
      - .. image:: https://static.pepy.tech/badge/html5lib
            :alt: html5lib total downloads
            :target: https://pepy.tech/project/html5lib
    - - 10
      - :doc:`html2text <html2text>`
      - `docs <https://github.com/Alir3z4/html2text>`__
      - .. image:: https://static.pepy.tech/badge/html2text/month
            :alt: html2text monthly downloads
            :target: https://pepy.tech/project/html2text
      - .. image:: https://static.pepy.tech/badge/html2text
            :alt: html2text total downloads
            :target: https://pepy.tech/project/html2text
    - - 11
      - :doc:`lxml-html-clean <lxml-html-clean>`
      - `docs <https://lxml-html-clean.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/lxml_html_clean/month
            :alt: lxml_html_clean monthly downloads
            :target: https://pepy.tech/project/lxml_html_clean
      - .. image:: https://static.pepy.tech/badge/lxml_html_clean
            :alt: lxml_html_clean total downloads
            :target: https://pepy.tech/project/lxml_html_clean
    - - 12
      - :doc:`w3lib <w3lib>`
      - `docs <https://w3lib.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/w3lib/month
            :alt: w3lib monthly downloads
            :target: https://pepy.tech/project/w3lib
      - .. image:: https://static.pepy.tech/badge/w3lib
            :alt: w3lib total downloads
            :target: https://pepy.tech/project/w3lib
    - - 13
      - :doc:`trafilatura <trafilatura>`
      - `docs <https://trafilatura.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/trafilatura/month
            :alt: trafilatura monthly downloads
            :target: https://pepy.tech/project/trafilatura
      - .. image:: https://static.pepy.tech/badge/trafilatura
            :alt: trafilatura total downloads
            :target: https://pepy.tech/project/trafilatura
    - - 14
      - :doc:`selectolax <selectolax>`
      - `docs <https://github.com/rushter/selectolax>`__
      - .. image:: https://static.pepy.tech/badge/selectolax/month
            :alt: selectolax monthly downloads
            :target: https://pepy.tech/project/selectolax
      - .. image:: https://static.pepy.tech/badge/selectolax
            :alt: selectolax total downloads
            :target: https://pepy.tech/project/selectolax
    - - 15
      - :doc:`parsel <parsel>`
      - `docs <https://parsel.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/parsel/month
            :alt: parsel monthly downloads
            :target: https://pepy.tech/project/parsel
      - .. image:: https://static.pepy.tech/badge/parsel
            :alt: parsel total downloads
            :target: https://pepy.tech/project/parsel
    - - 16
      - :doc:`pyquery <pyquery>`
      - `docs <https://pyquery.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/pyquery/month
            :alt: pyquery monthly downloads
            :target: https://pepy.tech/project/pyquery
      - .. image:: https://static.pepy.tech/badge/pyquery
            :alt: pyquery total downloads
            :target: https://pepy.tech/project/pyquery
    - - 17
      - :doc:`dominate <dominate>`
      - `docs <https://github.com/Knio/dominate>`__
      - .. image:: https://static.pepy.tech/badge/dominate/month
            :alt: dominate monthly downloads
            :target: https://pepy.tech/project/dominate
      - .. image:: https://static.pepy.tech/badge/dominate
            :alt: dominate total downloads
            :target: https://pepy.tech/project/dominate
    - - 18
      - :doc:`inscriptis <inscriptis>`
      - `docs <https://inscriptis.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/inscriptis/month
            :alt: inscriptis monthly downloads
            :target: https://pepy.tech/project/inscriptis
      - .. image:: https://static.pepy.tech/badge/inscriptis
            :alt: inscriptis total downloads
            :target: https://pepy.tech/project/inscriptis
    - - 19
      - :doc:`readability-lxml <readability-lxml>`
      - `docs <https://github.com/buriy/python-readability>`__
      - .. image:: https://static.pepy.tech/badge/readability-lxml/month
            :alt: readability-lxml monthly downloads
            :target: https://pepy.tech/project/readability-lxml
      - .. image:: https://static.pepy.tech/badge/readability-lxml
            :alt: readability-lxml total downloads
            :target: https://pepy.tech/project/readability-lxml
    - - 20
      - :doc:`html-text <html-text>`
      - `docs <https://github.com/zytedata/html-text>`__
      - .. image:: https://static.pepy.tech/badge/html-text/month
            :alt: html-text monthly downloads
            :target: https://pepy.tech/project/html-text
      - .. image:: https://static.pepy.tech/badge/html-text
            :alt: html-text total downloads
            :target: https://pepy.tech/project/html-text
    - - 21
      - :doc:`resiliparse <resiliparse>`
      - `docs <https://resiliparse.chatnoir.eu/>`__
      - .. image:: https://static.pepy.tech/badge/resiliparse/month
            :alt: resiliparse monthly downloads
            :target: https://pepy.tech/project/resiliparse
      - .. image:: https://static.pepy.tech/badge/resiliparse
            :alt: resiliparse total downloads
            :target: https://pepy.tech/project/resiliparse
    - - 22
      - :doc:`newspaper3k <newspaper3k>`
      - `docs <https://newspaper.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/newspaper3k/month
            :alt: newspaper3k monthly downloads
            :target: https://pepy.tech/project/newspaper3k
      - .. image:: https://static.pepy.tech/badge/newspaper3k
            :alt: newspaper3k total downloads
            :target: https://pepy.tech/project/newspaper3k
    - - 23
      - :doc:`html-sanitizer <html-sanitizer>`
      - `docs <https://github.com/matthiask/html-sanitizer>`__
      - .. image:: https://static.pepy.tech/badge/html-sanitizer/month
            :alt: html-sanitizer monthly downloads
            :target: https://pepy.tech/project/html-sanitizer
      - .. image:: https://static.pepy.tech/badge/html-sanitizer
            :alt: html-sanitizer total downloads
            :target: https://pepy.tech/project/html-sanitizer
    - - 24
      - :doc:`yattag <yattag>`
      - `docs <https://www.yattag.org/>`__
      - .. image:: https://static.pepy.tech/badge/yattag/month
            :alt: yattag monthly downloads
            :target: https://pepy.tech/project/yattag
      - .. image:: https://static.pepy.tech/badge/yattag
            :alt: yattag total downloads
            :target: https://pepy.tech/project/yattag
    - - 25
      - :doc:`extruct <extruct>`
      - `docs <https://github.com/scrapinghub/extruct>`__
      - .. image:: https://static.pepy.tech/badge/extruct/month
            :alt: extruct monthly downloads
            :target: https://pepy.tech/project/extruct
      - .. image:: https://static.pepy.tech/badge/extruct
            :alt: extruct total downloads
            :target: https://pepy.tech/project/extruct
    - - 26
      - :doc:`htpy <htpy>`
      - `docs <https://htpy.dev/>`__
      - .. image:: https://static.pepy.tech/badge/htpy/month
            :alt: htpy monthly downloads
            :target: https://pepy.tech/project/htpy
      - .. image:: https://static.pepy.tech/badge/htpy
            :alt: htpy total downloads
            :target: https://pepy.tech/project/htpy
    - - 27
      - :doc:`mechanicalsoup <mechanicalsoup>`
      - `docs <https://mechanicalsoup.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/MechanicalSoup/month
            :alt: MechanicalSoup monthly downloads
            :target: https://pepy.tech/project/MechanicalSoup
      - .. image:: https://static.pepy.tech/badge/MechanicalSoup
            :alt: MechanicalSoup total downloads
            :target: https://pepy.tech/project/MechanicalSoup
    - - 28
      - :doc:`airium <airium>`
      - `docs <https://gitlab.com/kamichal/airium>`__
      - .. image:: https://static.pepy.tech/badge/airium/month
            :alt: airium monthly downloads
            :target: https://pepy.tech/project/airium
      - .. image:: https://static.pepy.tech/badge/airium
            :alt: airium total downloads
            :target: https://pepy.tech/project/airium
    - - 29
      - :doc:`html5-parser <html5-parser>`
      - `docs <https://html5-parser.readthedocs.io/>`__
      - .. image:: https://static.pepy.tech/badge/html5-parser/month
            :alt: html5-parser monthly downloads
            :target: https://pepy.tech/project/html5-parser
      - .. image:: https://static.pepy.tech/badge/html5-parser
            :alt: html5-parser total downloads
            :target: https://pepy.tech/project/html5-parser
    - - 30
      - :doc:`metadata_parser <metadata_parser>`
      - `docs <https://github.com/jvanasco/metadata_parser>`__
      - .. image:: https://static.pepy.tech/badge/metadata_parser/month
            :alt: metadata_parser monthly downloads
            :target: https://pepy.tech/project/metadata_parser
      - .. image:: https://static.pepy.tech/badge/metadata_parser
            :alt: metadata_parser total downloads
            :target: https://pepy.tech/project/metadata_parser
    - - 31
      - :doc:`stdlib <stdlib>`
      - `docs <https://docs.python.org/3/library/html.parser.html>`__
      - Bundled with Python
      - --

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
    pyquery
    dominate
    inscriptis
    readability-lxml
    html-text
    resiliparse
    newspaper3k
    html-sanitizer
    yattag
    extruct
    htpy
    mechanicalsoup
    airium
    html5-parser
    metadata_parser
    stdlib
