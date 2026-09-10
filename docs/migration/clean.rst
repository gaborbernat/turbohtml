#######
 Clean
#######

Move sanitizing, linkifying, and minifying to turbohtml.

Use ``transform_node`` to compose cleanup on a parsed tree before traversal. ``collapse_whitespace_node`` and
``strip_comments_node`` mutate; ``sanitize_node`` returns a copy. Retain the composed root. The
:doc:`/how-to/transforming-trees` guide covers stage ordering and child serialization.

.. toctree::
    :maxdepth: 1

    linkify-it-py
    urlextract
    bleach
    phonenumbers
    nh3
    lxml-html-clean
    rcssmin
    rjsmin
    jsmin
    minify-html
    htmlmin
    csscompressor
    html-sanitizer
    calmjs-parse
    html5validator
    lightningcss
    sanitize-html
    dompurify
