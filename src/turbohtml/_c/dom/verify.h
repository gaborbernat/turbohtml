/* The tree invariant check behind the fuzz operation programs (issue #1017). A program calls it after every
   operation, so a broken link, a stale wrapper slot, a NodeIterator pointer that left its root, or a cache stamped
   from a future version reports at the step that caused it rather than at a later crash. */

#ifndef TURBOHTML_DOM_VERIFY_H
#define TURBOHTML_DOM_VERIFY_H

#include "dom/tree.h"

/* How many checks of each family failed. Each count is a sum of comparisons instead of an early exit, so one call
   reports every family that broke. */
typedef struct {
    Py_ssize_t links;      /* parent, sibling and last-child links that disagree */
    Py_ssize_t identities; /* creation stamps from outside this tree, plus the caller's per-node checks */
    Py_ssize_t iterators;  /* NodeIterator pointers outside their root */
    Py_ssize_t versions;   /* version counters out of order */
} th_tree_violations;

/* Walk every node under the topmost ancestor of start, passing each to visit for the caller's own per-node checks,
   then check the tree's registered NodeIterators and version counters. The caller holds the tree's critical
   section. */
void th_tree_verify(th_tree *tree, th_node *start, Py_ssize_t (*visit)(void *context, th_node *node), void *context,
                    th_tree_violations *found);

#endif /* TURBOHTML_DOM_VERIFY_H */
