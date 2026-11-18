``text`` on an element or text node whose only text is one run of the parsed input now reads that run in place, instead
of copying it into the tree first, so the first read is several times faster.
