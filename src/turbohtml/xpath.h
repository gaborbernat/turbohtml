/* XPath 1.0 over the turbohtml DOM (issue #179).

   This header is the seam between the engine and the rest of the module. The
   engine compiles a query string to an immutable program (a flat arena of tagged
   AST ops) once, then evaluates it many times against trees; the compiled program
   holds no tree pointers and no mutable state, so it is shareable across threads
   and lives in a per-handle cache like the CSS selector engine's.

   Phase 1 lands the front end only: the lexer and recursive-descent parser that
   build the arena AST, plus xp_dump for the conformance hook that the parser tests
   diff against. Evaluation and the Python xpath()/xpath_one() surface follow in
   later phases. */

#ifndef TURBOHTML_XPATH_H
#define TURBOHTML_XPATH_H

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdint.h>

typedef struct xp_program xp_program;

/* Compile an XPath expression given as code points. Returns the program, or NULL
   on a syntax error with a NUL-terminated message written into errbuf (errlen is
   its capacity). The source is not retained; names and literals are copied. */
xp_program *xp_compile(const Py_UCS4 *src, Py_ssize_t len, char *errbuf, size_t errlen);

void xp_free(xp_program *prog);

/* Render the compiled AST as a canonical S-expression (UCS4 code points), the form
   the parser tests assert against. PyMem-allocated; *out_len receives the length.
   NULL on allocation failure. */
Py_UCS4 *xp_dump(const xp_program *prog, Py_ssize_t *out_len);

/* A member of an evaluated node-set: a tree node, or one of its attributes when
   attr >= 0 (the index into node->attrs). attr == -1 means the node itself. */
struct th_node;
typedef struct {
    struct th_node *node;
    Py_ssize_t attr;
} xp_item;

typedef struct {
    xp_item *items;
    Py_ssize_t len;
    Py_ssize_t cap;
} xp_nodeset;

void xp_nodeset_free(xp_nodeset *ns);

/* Evaluate a location-path program against a context node, collecting the result
   node-set (document-ordered, duplicate-free) into *out. Returns 0 on success.
   Returns -2 for a construct this phase does not implement yet (predicates,
   operators, functions, unions, filter expressions, the following/preceding/
   namespace axes), with *feature set to a short name for the message. Returns -1
   on allocation failure. */
struct th_tree;
int xp_eval_nodeset(const xp_program *prog, struct th_tree *tree, struct th_node *context, xp_nodeset *out,
                    const char **feature);

#endif /* TURBOHTML_XPATH_H */
