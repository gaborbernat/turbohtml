/* WHATWG HTML tree construction: pure C, no Python objects.

   This file is the algorithm half of the parser: it drives the tokenizer state
   machine (tokenizer_sm.h), applies the WHATWG tree-construction rules, and
   builds a node tree. Like the tokenizer it creates no PyObjects; the Python
   layer in treebuilder_type.c walks the finished C tree and wraps only the
   nodes the caller touches.

   Nodes are bump-allocated from an arena owned by the tree and freed in one
   shot, so there is no per-node malloc/free and ownership is trivial. Element
   identity is an interned integer atom (tag_atom.h), so every scope and
   category test in the algorithm is an integer compare, never a strcmp. */

#ifndef TURBOHTML_TREEBUILDER_H
#define TURBOHTML_TREEBUILDER_H

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "attr_atom.h"
#include "tag_atom.h"
#include "tokenizer_sm.h"

enum th_node_type {
    TH_NODE_DOCUMENT,
    TH_NODE_ELEMENT,
    TH_NODE_TEXT,
    TH_NODE_COMMENT,
    TH_NODE_DOCTYPE,
    TH_NODE_CONTENT, /* a <template>'s content document fragment */
};

/* An attribute on an element node. The name is interned to an atom: a static
   compile-time id for common names (attr_atom.h), or a per-tree dynamic id for
   the rest. attr_record() recovers the name bytes for serialization and
   Element.attrs, so every name match the finder and selector do is an integer
   compare, never a strcmp. */
typedef struct {
    uint32_t name_atom;
    Py_UCS4 *value; /* code points, value_len of them; NULL when valueless */
    Py_ssize_t value_len;
} th_node_attr;

/* A tree node. Pointer-linked siblings + first/last child + parent, the layout
   every fast parser (lexbor, Go x/net/html, html5ever) converges on. Text and
   comment payloads are code-point buffers; elements carry an interned atom plus
   the original tag spelling for serialization of non-atom (unknown) tags. */
typedef struct th_node th_node;
enum th_ns {
    TH_NS_HTML,
    TH_NS_SVG,
    TH_NS_MATHML,
};

struct th_node {
    enum th_node_type type;
    uint16_t atom;     /* TH_TAG_* for elements, else TH_TAG_UNKNOWN */
    uint8_t tag_flags; /* category bitmask from the atom table */
    uint8_t ns;        /* enum th_ns: HTML / SVG / MathML */
    th_node *parent;
    th_node *first_child;
    th_node *last_child;
    th_node *prev_sibling;
    th_node *next_sibling;
    /* element: tag name; text/comment: payload; doctype: name */
    Py_UCS4 *text;
    Py_ssize_t text_len;
    th_node_attr *attrs;
    Py_ssize_t attr_count;
};

typedef struct th_tree th_tree;

/* Parse a whole document. kind/data/length are a borrowed PyUnicode buffer that
   must outlive the returned tree (its slice text points into it). Returns NULL
   only on allocation failure (no Python error is set). */
th_tree *th_tree_parse(int kind, const void *data, Py_ssize_t length);

/* Create an empty tree to own programmatically constructed nodes. Returns NULL on
   allocation failure (no Python error is set). */
th_tree *th_tree_new(void);

/* Construct a text/comment/doctype node (by enum th_node_type) owning a copy of
   the data code points in the tree's arena. NULL on allocation failure. */
th_node *th_tree_make_data_node(th_tree *tree, int type, const Py_UCS4 *data, Py_ssize_t len);

/* Parse an HTML fragment as if set as the innerHTML of the given context element
   (e.g. "td", or "svg path"). The returned tree serializes the context root's
   children. context is a NUL-free ASCII name; context_len its length. */
th_tree *th_tree_parse_fragment(int kind, const void *data, Py_ssize_t length, const char *context,
                                Py_ssize_t context_len);

void th_tree_free(th_tree *tree);

/* Serialize the tree in the html5lib tree-construction "#document" format (one
   "| " indented line per node) into a freshly PyMem-allocated UCS4 buffer;
   *out_len receives the length. Returns NULL on allocation failure. Used by the
   conformance harness to diff against the .dat expectations. */
Py_UCS4 *th_tree_serialize(th_tree *tree, Py_ssize_t *out_len);

/* --- navigable-tree accessors for the public Python Node API --- */

/* The document (root) node; its children are the doctype/comments and <html>.
   For a fragment the children of the context root are exposed instead. */
th_node *th_tree_document(th_tree *tree);

/* Materialize one text/comment/doctype node's own character data (realizing a
   zero-copy span on demand) into a freshly PyMem-allocated UCS4 buffer.
   *out_len receives the length; returns NULL on allocation failure. */
Py_UCS4 *th_node_data(th_tree *tree, th_node *node, Py_ssize_t *out_len);

/* The concatenated character data of every Text descendant of node, in document
   order. PyMem-allocated; *out_len receives the length. NULL on failure. */
Py_UCS4 *th_node_text(th_tree *tree, th_node *node, Py_ssize_t *out_len);

/* Serialize node and its subtree as HTML (the WHATWG fragment serialization).
   For the document node this is the whole-document markup. PyMem-allocated;
   *out_len receives the length. NULL on failure. */
Py_UCS4 *th_node_html(th_tree *tree, th_node *node, Py_ssize_t *out_len);

/* Serialize only node's children (its inner HTML), WHATWG-conformant and
   compact. PyMem-allocated; *out_len receives the length. NULL on failure. */
Py_UCS4 *th_node_inner_html(th_tree *tree, th_node *node, Py_ssize_t *out_len);

/* Serialize node and its subtree under a chosen escape formatter (0 WHATWG,
   1 minimal, 2 named entities). When indent is non-NULL it is the per-level
   whitespace unit for pretty output; NULL emits the compact form. PyMem-
   allocated; *out_len receives the length. NULL on failure. */
Py_UCS4 *th_node_serialize(th_tree *tree, th_node *node, int formatter, const Py_UCS4 *indent, Py_ssize_t indent_len,
                           Py_ssize_t *out_len);

/* The doctype's public and system identifiers as slices of the node's own text;
   returns 1 with the four out params set when present, 0 for a name-only doctype. */
int th_node_doctype_ids(th_node *node, const Py_UCS4 **public_id, Py_ssize_t *public_len, const Py_UCS4 **system_id,
                        Py_ssize_t *system_len);

/* The interned name bytes (NUL-terminated UTF-8) for an attribute's name_atom;
   *out_len receives the length. Resolves a static atom from the generated table
   and a dynamic one from the tree's intern table. */
const char *th_attr_name(th_tree *tree, uint32_t name_atom, Py_ssize_t *out_len);

/* Resolve a query attribute name (UTF-8 bytes) to the atom an element in this
   tree would carry for it, or UINT32_MAX when no element has that name. */
uint32_t th_attr_lookup(th_tree *tree, const char *bytes, Py_ssize_t len);

/* Resolve a lowercased tag name (UTF-8 bytes) to its atom, or TH_TAG_UNKNOWN.
   bytes must point at one readable byte (len >= 1); the selector parser never
   forms an empty type name. */
uint16_t th_tag_lookup(const char *bytes, Py_ssize_t len);

#endif /* TURBOHTML_TREEBUILDER_H */
