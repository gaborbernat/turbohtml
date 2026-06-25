#######
 Clean
#######

.. module:: turbohtml.clean

Clean untrusted or raw HTML: sanitize it against an allowlist and rewrite bare URLs into links. Sanitizing is a
successor to ``bleach.clean`` -- build a :class:`Policy` (or take a preset), then sanitize; a non-overridable baseline
removes scripting elements, event-handler attributes, and ``javascript:`` URLs regardless of the policy. Linkifying is a
successor to `bleach.linkify <https://github.com/mozilla/bleach>`_ -- it finds URLs and email addresses and wraps them
in ``<a>`` links, HTML-aware so it never links inside an existing ``<a>``, a raw-text element, or a caller's
``skip_tags``.

.. autofunction:: sanitize

.. autoclass:: Sanitizer
    :members: sanitize

.. autoclass:: Policy
    :members: strict, basic, relaxed

.. autoclass:: OnDisallowed
    :members:

************
 Linkifying
************

A :class:`Linkify` configuration object carries the knobs: a callback receives each generated :class:`Link` and returns
it to keep the link or ``None`` to leave the text bare, ``process_existing`` runs the callbacks over ``<a>`` tags
already in the input (a callback reads ``Link.existing`` to tell the two apart), ``extra_tlds`` extends bare-domain
detection beyond the built-in IANA table, and ``schemes`` restricts which explicit-scheme URLs autolink.

.. autofunction:: linkify

.. autoclass:: Linkify
    :members:

.. autoclass:: Linker
    :members: linkify

.. autoclass:: Link

.. autofunction:: nofollow

.. autofunction:: target_blank

To only *locate* links in plain text rather than rewrite HTML, use :class:`Detector`. It returns a :class:`LinkSpan` for
each match and accepts custom ``tlds`` and scheme-less ``schemes``.

.. autoclass:: Detector
    :members: find, has_link

.. autoclass:: LinkSpan
    :members:

turbohtml.migration.bleach
==========================

.. module:: turbohtml.migration.bleach

A drop-in for ``bleach.clean`` for projects migrating off bleach. It translates bleach's arguments onto a
:class:`~turbohtml.clean.Policy`; the safety baseline still applies, so an ``attributes`` callable cannot re-admit an
event handler or a ``javascript:`` URL.

.. autofunction:: clean
