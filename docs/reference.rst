###########
 Reference
###########

.. automodule:: turbohtml
    :members:
    :exclude-members: TokenType
    :special-members: __version__

.. autoclass:: turbohtml.TokenType
    :members:
    :undoc-members:

******************
 turbohtml.markup
******************

.. module:: turbohtml.markup

A safe-string for composing HTML, a drop-in for markupsafe's public surface. Import it in place of ``markupsafe``.
``Markup`` overrides every ``str`` method that returns text so the result stays a ``Markup``; the methods below are the
turbohtml-specific ones, the rest mirror :class:`str`.

.. autofunction:: escape

.. autofunction:: escape_silent

.. autofunction:: soft_str

.. autoclass:: Markup
    :members: escape, format, join, striptags, unescape

.. autoclass:: EscapeFormatter
    :members: format_field
