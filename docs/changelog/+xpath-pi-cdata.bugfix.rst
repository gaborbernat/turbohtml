XPath gives a processing instruction its data as string-value and a CDATA section its text, so ``string()``,
``normalize-space()``, comparisons and ``text()`` see the character data of CDATA sections as XPath 1.0 defines it.
Adjacent text and CDATA sections count as one text node, and ``xsl:value-of``, ``xsl:copy-of``, ``xsl:number`` and
``strip-space`` follow the same rule.
