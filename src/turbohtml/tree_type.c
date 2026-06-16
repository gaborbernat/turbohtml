/* The navigable Node tree: the public, typed surface over the C parser.

   A parse() call builds a th_tree in the arena and hands back a Document. A
   private _TreeHandle keeps the tree and the input string it borrows from alive;
   every Node holds a strong reference to that handle, so the whole tree survives
   as long as any node reachable from it. Traversal creates Node wrappers lazily:
   walking into a child or sibling allocates one small object pointing at the
   existing arena node, never copying the subtree.

   The wrappers form a sealed hierarchy (Document / Element / Text / Comment /
   Doctype, plus the bare Node for a <template>'s content fragment) sharing one C
   struct; the node's th_node type selects which Python type wraps it. */

#include "tokenizer_py.h"

#include "ascii.h"
#include "encoding.h"
#include "selector.h"
#include "treebuilder.h"

typedef struct {
    PyObject_HEAD th_tree *tree;
    PyObject *source;   /* the input str whose storage the tree's spans borrow */
    PyObject *encoding; /* the resolved encoding name for bytes input, else None */
} HandleObject;

typedef struct {
    PyObject_HEAD PyObject *handle; /* _TreeHandle keeping tree + source alive */
    th_node *node;
} NodeObject;

enum walk_mode { WALK_DESCENDANTS, WALK_ANCESTORS, WALK_NEXT_SIBLINGS, WALK_PREVIOUS_SIBLINGS, WALK_PRECEDING };

/* The axes find()/find_all() search over; the order matches the Axis enum members
   so a member's value is its enum index. */
enum th_axis {
    TH_AXIS_DESCENDANTS,
    TH_AXIS_CHILDREN,
    TH_AXIS_ANCESTORS,
    TH_AXIS_NEXT_SIBLINGS,
    TH_AXIS_PREVIOUS_SIBLINGS,
    TH_AXIS_FOLLOWING,
    TH_AXIS_PRECEDING,
};

typedef struct {
    PyObject_HEAD PyObject *handle;
    th_node *root;    /* subtree bound for pre-order walks (unused for ancestors) */
    th_node *current; /* next node to yield, or NULL when exhausted */
    int mode;
} WalkerObject;

typedef struct {
    PyObject_HEAD PyObject *handle;
    th_node *root;    /* the subtree whose Text descendants are yielded */
    th_node *current; /* next node to consider in pre-order, or NULL when exhausted */
    int strip;        /* drop surrounding whitespace and skip blank runs */
} StringWalkerObject;

static module_state *state_of(PyObject *self) {
    return PyType_GetModuleState(Py_TYPE(self));
}

static th_tree *tree_of(PyObject *self) {
    return ((HandleObject *)((NodeObject *)self)->handle)->tree;
}

static PyObject *ucs4_to_str(const Py_UCS4 *data, Py_ssize_t len) {
    return PyUnicode_FromKindAndData(PyUnicode_4BYTE_KIND, data, len);
}

/* Realize one of the th_node_* accessors (which return a PyMem UCS4 buffer) into
   a str, freeing the buffer. */
static PyObject *str_from_accessor(Py_UCS4 *(*accessor)(th_tree *, th_node *, Py_ssize_t *), th_tree *tree,
                                   th_node *node) {
    Py_ssize_t len;
    Py_UCS4 *buf = accessor(tree, node, &len);
    if (buf == NULL) {           /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *result = ucs4_to_str(buf, len);
    PyMem_Free(buf);
    return result;
}

/* --------------------------------------------------------- node lifetime */

static PyObject *type_for_node(module_state *state, const th_node *node) {
    switch (node->type) { /* GCOVR_EXCL_BR_LINE: th_node_type is exhaustive; the implicit default is unreachable */
    case TH_NODE_DOCUMENT:
        return state->document_type;
    case TH_NODE_ELEMENT:
        return state->element_type;
    case TH_NODE_TEXT:
        return state->text_type;
    case TH_NODE_COMMENT:
        return state->comment_type;
    case TH_NODE_DOCTYPE:
        return state->doctype_type;
    case TH_NODE_CONTENT:
        break; /* a template's content fragment wraps as the bare Node */
    }
    return state->node_type;
}

static PyObject *node_wrap(module_state *state, PyObject *handle, th_node *node) {
    if (node == NULL) {
        Py_RETURN_NONE;
    }
    PyTypeObject *type = (PyTypeObject *)type_for_node(state, node);
    NodeObject *self = (NodeObject *)type->tp_alloc(type, 0);
    if (self == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;    /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    self->handle = Py_NewRef(handle);
    self->node = node;
    return (PyObject *)self;
}

static void node_dealloc(PyObject *self) {
    PyTypeObject *type = Py_TYPE(self);
    Py_DECREF(((NodeObject *)self)->handle);
    type->tp_free(self);
    Py_DECREF(type);
}

static int is_node(PyObject *obj, module_state *state) {
    return PyObject_TypeCheck(obj, (PyTypeObject *)state->node_type);
}

static PyObject *node_richcompare(PyObject *left, PyObject *right, int op) {
    module_state *state = state_of(left);
    if (op != Py_EQ && op != Py_NE) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    if (!is_node(right, state)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    int equal = ((NodeObject *)left)->node == ((NodeObject *)right)->node;
    return PyBool_FromLong(op == Py_EQ ? equal : !equal);
}

static Py_hash_t node_hash(PyObject *self) {
    Py_hash_t hash = (Py_hash_t)(uintptr_t)((NodeObject *)self)->node;
    return hash == -1 ? -2 : hash; /* GCOVR_EXCL_BR_LINE: an arena pointer is never (Py_hash_t)-1 */
}

/* --------------------------------------------------------------- walking */

static th_node *preorder_next(th_node *current, th_node *root) {
    if (current->first_child != NULL) {
        return current->first_child;
    }
    while (current != root) {
        if (current->next_sibling != NULL) {
            return current->next_sibling;
        }
        current = current->parent;
    }
    return NULL;
}

/* The node before this one in document order: the deepest last descendant of the
   previous sibling, else the parent. */
static th_node *previous_element(th_node *node) {
    if (node->prev_sibling != NULL) {
        th_node *back = node->prev_sibling;
        while (back->last_child != NULL) {
            back = back->last_child;
        }
        return back;
    }
    return node->parent;
}

/* The node after this one's whole subtree in document order: the next sibling, or
   the nearest ancestor's next sibling, or NULL at the end of the document. */
static th_node *subtree_next(th_node *node) {
    while (node != NULL) {
        if (node->next_sibling != NULL) {
            return node->next_sibling;
        }
        node = node->parent;
    }
    return NULL;
}

static int is_ancestor(th_node *candidate, th_node *node) {
    for (th_node *parent = node->parent; parent != NULL; parent = parent->parent) {
        if (parent == candidate) {
            return 1;
        }
    }
    return 0;
}

/* Walk back in document order from current, skipping origin's ancestors so the
   preceding axis stays disjoint from the ancestors axis. */
static th_node *preceding_skip(th_node *current, th_node *origin) {
    while (current != NULL && is_ancestor(current, origin)) {
        current = previous_element(current);
    }
    return current;
}

static PyObject *walker_new(module_state *state, PyObject *handle, th_node *start, th_node *root, int mode) {
    PyTypeObject *type = (PyTypeObject *)state->walker_type;
    WalkerObject *self = (WalkerObject *)type->tp_alloc(type, 0);
    if (self == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;    /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    self->handle = Py_NewRef(handle);
    self->root = root;
    self->current = start;
    self->mode = mode;
    return (PyObject *)self;
}

static void walker_dealloc(PyObject *self) {
    PyTypeObject *type = Py_TYPE(self);
    Py_DECREF(((WalkerObject *)self)->handle);
    type->tp_free(self);
    Py_DECREF(type);
}

static PyObject *walker_next(PyObject *self) {
    WalkerObject *walker = (WalkerObject *)self;
    if (walker->current == NULL) {
        return NULL;
    }
    th_node *node = walker->current;
    switch (walker->mode) {
    case WALK_ANCESTORS:
        walker->current = node->parent;
        break;
    case WALK_NEXT_SIBLINGS:
        walker->current = node->next_sibling;
        break;
    case WALK_PREVIOUS_SIBLINGS:
        walker->current = node->prev_sibling;
        break;
    case WALK_PRECEDING:
        walker->current = preceding_skip(previous_element(node), walker->root);
        break;
    default: /* WALK_DESCENDANTS, and the following axis bounded by a NULL root */
        walker->current = preorder_next(node, walker->root);
        break;
    }
    return node_wrap(state_of(self), walker->handle, node);
}

static PyType_Slot walker_slots[] = {
    {Py_tp_dealloc, walker_dealloc},
    {Py_tp_iter, PyObject_SelfIter},
    {Py_tp_iternext, walker_next},
    {0, NULL},
};

static PyType_Spec walker_spec = {
    .name = "turbohtml._html._NodeIterator",
    .basicsize = sizeof(WalkerObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION,
    .slots = walker_slots,
};

static PyObject *string_walker_new(module_state *state, PyObject *handle, th_node *node, int strip) {
    PyTypeObject *type = (PyTypeObject *)state->string_walker_type;
    StringWalkerObject *self = (StringWalkerObject *)type->tp_alloc(type, 0);
    if (self == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;    /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    self->handle = Py_NewRef(handle);
    self->root = node;
    self->current = node->first_child;
    self->strip = strip;
    return (PyObject *)self;
}

static void string_walker_dealloc(PyObject *self) {
    PyTypeObject *type = Py_TYPE(self);
    Py_DECREF(((StringWalkerObject *)self)->handle);
    type->tp_free(self);
    Py_DECREF(type);
}

static PyObject *string_walker_next(PyObject *self) {
    StringWalkerObject *walker = (StringWalkerObject *)self;
    th_tree *tree = ((HandleObject *)walker->handle)->tree;
    while (walker->current != NULL) {
        th_node *node = walker->current;
        walker->current = preorder_next(node, walker->root);
        if (node->type != TH_NODE_TEXT) {
            continue;
        }
        Py_ssize_t len;
        Py_UCS4 *buf = th_node_data(tree, node, &len);
        if (buf == NULL) {           /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        Py_ssize_t start = 0;
        Py_ssize_t stop = len;
        if (walker->strip) {
            while (start < stop && is_space(buf[start])) {
                start++;
            }
            while (stop > start && is_space(buf[stop - 1])) {
                stop--;
            }
            if (stop == start) {
                PyMem_Free(buf);
                continue;
            }
        }
        PyObject *text = ucs4_to_str(buf + start, stop - start);
        PyMem_Free(buf);
        return text;
    }
    return NULL;
}

static PyType_Slot string_walker_slots[] = {
    {Py_tp_dealloc, string_walker_dealloc},
    {Py_tp_iter, PyObject_SelfIter},
    {Py_tp_iternext, string_walker_next},
    {0, NULL},
};

static PyType_Spec string_walker_spec = {
    .name = "turbohtml._html._StringIterator",
    .basicsize = sizeof(StringWalkerObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION,
    .slots = string_walker_slots,
};

/* ------------------------------------------------- shared Node behavior */

static PyObject *node_get_parent(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return node_wrap(state_of(self), node->handle, node->node->parent);
}

static PyObject *node_get_next_sibling(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return node_wrap(state_of(self), node->handle, node->node->next_sibling);
}

static PyObject *node_get_previous_sibling(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return node_wrap(state_of(self), node->handle, node->node->prev_sibling);
}

static PyObject *node_children_tuple(PyObject *self) {
    NodeObject *node = (NodeObject *)self;
    module_state *state = state_of(self);
    Py_ssize_t count = 0;
    for (th_node *child = node->node->first_child; child != NULL; child = child->next_sibling) {
        count++;
    }
    PyObject *tuple = PyTuple_New(count);
    if (tuple == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;     /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    Py_ssize_t index = 0;
    for (th_node *child = node->node->first_child; child != NULL; child = child->next_sibling) {
        PyObject *wrapped = node_wrap(state, node->handle, child);
        if (wrapped == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            Py_DECREF(tuple);  /* GCOVR_EXCL_LINE: allocation-failure path */
            return NULL;       /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        PyTuple_SET_ITEM(tuple, index++, wrapped);
    }
    return tuple;
}

static PyObject *node_get_children(PyObject *self, void *Py_UNUSED(closure)) {
    return node_children_tuple(self);
}

static PyObject *node_get_descendants(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return walker_new(state_of(self), node->handle, node->node->first_child, node->node, WALK_DESCENDANTS);
}

static PyObject *node_get_ancestors(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return walker_new(state_of(self), node->handle, node->node->parent, NULL, WALK_ANCESTORS);
}

static PyObject *node_get_next_siblings(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return walker_new(state_of(self), node->handle, node->node->next_sibling, NULL, WALK_NEXT_SIBLINGS);
}

static PyObject *node_get_previous_siblings(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return walker_new(state_of(self), node->handle, node->node->prev_sibling, NULL, WALK_PREVIOUS_SIBLINGS);
}

static PyObject *node_get_following(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return walker_new(state_of(self), node->handle, subtree_next(node->node), NULL, WALK_DESCENDANTS);
}

static PyObject *node_get_preceding(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    th_node *start = preceding_skip(previous_element(node->node), node->node);
    return walker_new(state_of(self), node->handle, start, node->node, WALK_PRECEDING);
}

static PyObject *node_get_strings(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return string_walker_new(state_of(self), node->handle, node->node, 0);
}

static PyObject *node_get_stripped_strings(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    return string_walker_new(state_of(self), node->handle, node->node, 1);
}

static PyObject *node_get_text(PyObject *self, void *Py_UNUSED(closure)) {
    return str_from_accessor(th_node_text, tree_of(self), ((NodeObject *)self)->node);
}

static PyObject *node_get_html(PyObject *self, void *Py_UNUSED(closure)) {
    return str_from_accessor(th_node_html, tree_of(self), ((NodeObject *)self)->node);
}

static PyObject *node_get_inner_html(PyObject *self, void *Py_UNUSED(closure)) {
    return str_from_accessor(th_node_inner_html, tree_of(self), ((NodeObject *)self)->node);
}

static PyGetSetDef node_getset[] = {
    {"parent", node_get_parent, NULL, "the parent Element or Document, or None for the document root", NULL},
    {"children", node_get_children, NULL, "the child nodes as a tuple", NULL},
    {"next_sibling", node_get_next_sibling, NULL, "the following sibling node, or None", NULL},
    {"previous_sibling", node_get_previous_sibling, NULL, "the preceding sibling node, or None", NULL},
    {"descendants", node_get_descendants, NULL, "an iterator over every descendant in document order", NULL},
    {"ancestors", node_get_ancestors, NULL, "an iterator from parent up to the document", NULL},
    {"next_siblings", node_get_next_siblings, NULL, "an iterator over the following siblings in document order", NULL},
    {"previous_siblings", node_get_previous_siblings, NULL, "an iterator over the preceding siblings, nearest first",
     NULL},
    {"following", node_get_following, NULL,
     "an iterator over nodes after this one in document order, excluding its descendants", NULL},
    {"preceding", node_get_preceding, NULL,
     "an iterator over nodes before this one in document order, nearest first, excluding its ancestors", NULL},
    {"strings", node_get_strings, NULL, "an iterator over the text of every Text descendant", NULL},
    {"stripped_strings", node_get_stripped_strings, NULL,
     "strings with surrounding whitespace removed and blank runs skipped", NULL},
    {"text", node_get_text, NULL, "the concatenated character data of every Text descendant", NULL},
    {"html", node_get_html, NULL, "the HTML serialization of this node and its subtree", NULL},
    {"inner_html", node_get_inner_html, NULL, "the HTML serialization of this node's children", NULL},
    {NULL, NULL, NULL, NULL, NULL},
};

static Py_ssize_t node_length(PyObject *self) {
    Py_ssize_t count = 0;
    for (th_node *child = ((NodeObject *)self)->node->first_child; child != NULL; child = child->next_sibling) {
        count++;
    }
    return count;
}

static PyObject *node_item(PyObject *self, Py_ssize_t index) {
    NodeObject *node = (NodeObject *)self;
    th_node *child = node->node->first_child;
    for (Py_ssize_t step = 0; step < index && child != NULL; step++) {
        child = child->next_sibling;
    }
    if (child == NULL) {
        PyErr_SetString(PyExc_IndexError, "node child index out of range");
        return NULL;
    }
    return node_wrap(state_of(self), node->handle, child);
}

static PyObject *node_iter(PyObject *self) {
    PyObject *children = node_children_tuple(self);
    if (children == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;        /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *iterator = PyObject_GetIter(children);
    Py_DECREF(children);
    return iterator;
}

static int node_bool(PyObject *Py_UNUSED(self)) {
    return 1; /* a node is always truthy; emptiness is len(), not bool() */
}

/* ------------------------------------------------------------- repr ----- */

static PyObject *node_repr(PyObject *self) {
    th_node *node = ((NodeObject *)self)->node;
    switch (node->type) { /* GCOVR_EXCL_BR_LINE: th_node_type is exhaustive; the implicit default is unreachable */
    case TH_NODE_ELEMENT: {
        PyObject *tag = ucs4_to_str(node->text, node->text_len);
        if (tag == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return NULL;   /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        PyObject *repr = PyUnicode_FromFormat("Element(%R)", tag);
        Py_DECREF(tag);
        return repr;
    }
    case TH_NODE_TEXT:
    case TH_NODE_COMMENT:
    case TH_NODE_DOCTYPE: {
        PyObject *data = str_from_accessor(th_node_data, tree_of(self), node);
        if (data == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return NULL;    /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        const char *label = node->type == TH_NODE_TEXT ? "Text" : node->type == TH_NODE_COMMENT ? "Comment" : "Doctype";
        PyObject *repr = PyUnicode_FromFormat("%s(%R)", label, data);
        Py_DECREF(data);
        return repr;
    }
    case TH_NODE_DOCUMENT:
        return PyUnicode_FromString("Document()");
    case TH_NODE_CONTENT:
        break;
    }
    return PyUnicode_FromString("Node()");
}

/* find/find_all live on the base so a Document, an Element, or any container
   node answers them directly; the bodies sit further down with the matching
   machinery, forward-declared here. */
static PyObject *node_find(PyObject *self, PyObject *args, PyObject *kwargs);
static PyObject *node_find_all(PyObject *self, PyObject *args, PyObject *kwargs);
static PyObject *node_select(PyObject *self, PyObject *arg);
static PyObject *node_select_one(PyObject *self, PyObject *arg);
static PyObject *node_css_matches(PyObject *self, PyObject *arg);
static PyObject *node_css_closest(PyObject *self, PyObject *arg);

PyDoc_STRVAR(select_doc, "select(selector, /)\n--\n\n"
                         "Return the list of descendant Elements matching the CSS selector, in\n"
                         "document order.");

PyDoc_STRVAR(select_one_doc, "select_one(selector, /)\n--\n\n"
                             "Return the first descendant Element matching the CSS selector, or None.");

PyDoc_STRVAR(matches_doc, "matches(selector, /)\n--\n\n"
                          "Return whether this node is an Element matching the CSS selector,\n"
                          "evaluated against its own ancestors and siblings.");

PyDoc_STRVAR(closest_doc, "closest(selector, /)\n--\n\n"
                          "Return the nearest Element matching the CSS selector, testing this node\n"
                          "then each ancestor, or None.");

static PyObject *node_serialize(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *node_encode(PyObject *self, PyObject *args, PyObject *kwds);

PyDoc_STRVAR(serialize_doc, "serialize(*, formatter=Formatter.WHATWG, indent=None)\n--\n\n"
                            "Serialize this node and its subtree to a str. formatter chooses the\n"
                            "escape policy; indent, an int or string, switches to a pretty form that\n"
                            "adds whitespace and so does not preserve meaning.");

PyDoc_STRVAR(encode_doc, "encode(encoding='utf-8', *, formatter=Formatter.WHATWG, indent=None)\n--\n\n"
                         "Serialize this node and its subtree to bytes in the named encoding,\n"
                         "with the same formatter and indent controls as serialize().");

PyDoc_STRVAR(find_doc, "find(tag=None, /, *, axis=Axis.DESCENDANTS, attrs=None, class_=None, **filters)\n--\n\n"
                       "Return the first Element along axis matching the tag filter and every\n"
                       "attribute filter, or None. A filter is a str, bool, compiled regex,\n"
                       "callable, or a list of those.");

PyDoc_STRVAR(find_all_doc,
             "find_all(tag=None, /, *, axis=Axis.DESCENDANTS, attrs=None, class_=None, limit=None, **filters)\n--\n\n"
             "Return the list of Elements along axis matching the tag filter and every\n"
             "attribute filter, up to limit results.");

static PyMethodDef node_methods[] = {
    {"find", (PyCFunction)(void (*)(void))node_find, METH_VARARGS | METH_KEYWORDS, find_doc},
    {"find_all", (PyCFunction)(void (*)(void))node_find_all, METH_VARARGS | METH_KEYWORDS, find_all_doc},
    {"select", node_select, METH_O, select_doc},
    {"select_one", node_select_one, METH_O, select_one_doc},
    {"matches", node_css_matches, METH_O, matches_doc},
    {"closest", node_css_closest, METH_O, closest_doc},
    {"serialize", (PyCFunction)(void (*)(void))node_serialize, METH_VARARGS | METH_KEYWORDS, serialize_doc},
    {"encode", (PyCFunction)(void (*)(void))node_encode, METH_VARARGS | METH_KEYWORDS, encode_doc},
    {NULL, NULL, 0, NULL},
};

PyDoc_STRVAR(node_doc, "Common navigation shared by every node in a parsed tree. Text appears as\n"
                       "real child nodes (the WHATWG DOM shape), so there is no text/tail split.");

static PyType_Slot node_slots[] = {
    {Py_tp_doc, (void *)node_doc}, {Py_tp_dealloc, node_dealloc},
    {Py_tp_repr, node_repr},       {Py_tp_richcompare, node_richcompare},
    {Py_tp_hash, node_hash},       {Py_tp_getset, node_getset},
    {Py_tp_methods, node_methods}, {Py_tp_iter, node_iter},
    {Py_sq_length, node_length},   {Py_sq_item, node_item},
    {Py_nb_bool, node_bool},       {0, NULL},
};

static PyType_Spec node_spec = {
    .name = "turbohtml._html.Node",
    .basicsize = sizeof(NodeObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE | Py_TPFLAGS_DISALLOW_INSTANTIATION,
    .slots = node_slots,
};

/* --------------------------------------------------------------- Element */

/* Attribute names the HTML standard treats as space-separated token lists. They
   surface in Element.attrs as a list[str] instead of a single string, so class
   membership and similar reads hit a list rather than re-splitting. The set is by
   name (its interned atom), not by element; invalid markup such as <div rel> is
   the only case where that differs from a tag-specific table. */
static int attr_is_token_list(uint32_t name_atom) {
    switch (name_atom) {
    case TH_ATTR_CLASS:
    case TH_ATTR_REL:
    case TH_ATTR_REV:
    case TH_ATTR_HEADERS:
    case TH_ATTR_ACCESSKEY:
    case TH_ATTR_DROPZONE:
    case TH_ATTR_SIZES:
    case TH_ATTR_SANDBOX:
    case TH_ATTR_ARCHIVE:
    case TH_ATTR_ACCEPT_CHARSET:
        return 1;
    default:
        return 0;
    }
}

/* Split a token-list attribute value on ASCII whitespace, dropping empty runs:
   "  a  b " yields ["a", "b"] and "" yields []. */
static PyObject *split_token_list(const Py_UCS4 *value, Py_ssize_t value_len) {
    PyObject *tokens = PyList_New(0);
    if (tokens == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;      /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    Py_ssize_t cursor = 0;
    while (cursor < value_len) {
        while (cursor < value_len && is_space(value[cursor])) {
            cursor++;
        }
        Py_ssize_t start = cursor;
        while (cursor < value_len && !is_space(value[cursor])) {
            cursor++;
        }
        if (cursor > start) {
            PyObject *token = ucs4_to_str(&value[start], cursor - start);
            if (token == NULL || PyList_Append(tokens, token) < 0) { /* GCOVR_EXCL_BR_LINE: alloc failure */
                Py_XDECREF(token);                                   /* GCOVR_EXCL_LINE: alloc-failure path */
                Py_DECREF(tokens);                                   /* GCOVR_EXCL_LINE: alloc-failure path */
                return NULL;                                         /* GCOVR_EXCL_LINE: alloc-failure path */
            }
            Py_DECREF(token);
        }
    }
    return tokens;
}

/* Build the Element.attrs mapping: token-list attributes (class and friends)
   become a list[str], a valueless attribute is None, everything else is a str. */
static PyObject *build_attrs(th_tree *tree, const th_node *node) {
    PyObject *attrs = PyDict_New();
    if (attrs == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;     /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    for (Py_ssize_t attr_index = 0; attr_index < node->attr_count; attr_index++) {
        const th_node_attr *attr = &node->attrs[attr_index];
        Py_ssize_t name_len;
        const char *name_bytes = th_attr_name(tree, attr->name_atom, &name_len);
        PyObject *name = PyUnicode_DecodeUTF8(name_bytes, name_len, "strict");
        PyObject *value;
        if (attr->value == NULL) {
            value = Py_NewRef(Py_None);
        } else if (attr_is_token_list(attr->name_atom)) {
            value = split_token_list(attr->value, attr->value_len);
        } else {
            value = ucs4_to_str(attr->value, attr->value_len);
        }
        /* allocation failure cannot be forced from a test */
        if (name == NULL || value == NULL || PyDict_SetItem(attrs, name, value) < 0) { /* GCOVR_EXCL_BR_LINE */
            Py_XDECREF(name);  /* GCOVR_EXCL_LINE: alloc-failure path */
            Py_XDECREF(value); /* GCOVR_EXCL_LINE: alloc-failure path */
            Py_DECREF(attrs);  /* GCOVR_EXCL_LINE: alloc-failure path */
            return NULL;       /* GCOVR_EXCL_LINE: alloc-failure path */
        }
        Py_DECREF(name);
        Py_DECREF(value);
    }
    return attrs;
}

static PyObject *element_get_tag(PyObject *self, void *Py_UNUSED(closure)) {
    th_node *node = ((NodeObject *)self)->node;
    return ucs4_to_str(node->text, node->text_len);
}

static PyObject *element_get_namespace(PyObject *self, void *Py_UNUSED(closure)) {
    return Py_NewRef(state_of(self)->namespaces[((NodeObject *)self)->node->ns]);
}

static PyObject *element_get_attrs(PyObject *self, void *Py_UNUSED(closure)) {
    return build_attrs(tree_of(self), ((NodeObject *)self)->node);
}

static PyGetSetDef element_getset[] = {
    {"tag", element_get_tag, NULL, "the lowercased tag name", NULL},
    {"namespace", element_get_namespace, NULL, "the element's Namespace (HTML, SVG, or MATHML)", NULL},
    {"attrs", element_get_attrs, NULL,
     "the attributes as a dict; token-list attributes (class, rel, ...) map to a list[str], a valueless attribute "
     "maps to None",
     NULL},
    {NULL, NULL, NULL, NULL, NULL},
};

/* A compiled find()/find_all() query: the tag and class_ filters, the resolved
   (atom, filter) pairs for the named attribute filters, the axis to search, and
   the result cap. Every filter PyObject is borrowed from the live call. */
typedef struct {
    PyObject *tag;          /* tag filter, or NULL for no tag constraint */
    PyObject *class_filter; /* class_ filter, or NULL */
    enum th_axis axis;
    Py_ssize_t limit; /* -1 for unlimited */
    uint32_t *atoms;  /* resolved name atoms for the attribute filters */
    PyObject **filters;
    Py_ssize_t nattr;
    /* Fast path for a plain-string tag filter: resolve the name to an atom once
       so the per-node test is an integer compare instead of building a str for
       every element. tag_plain is set when tag is a single str; tag_atom is its
       atom, or TH_TAG_UNKNOWN for a name outside the table (then the rare
       unknown-atom elements are compared by name). */
    int tag_plain;
    uint16_t tag_atom;
    /* Fast path for a plain-string class_ filter: its code points are copied
       once so each element's class tokens are compared without building a str
       per token. class_ucs4 is NULL unless class_filter is a single str. */
    Py_UCS4 *class_ucs4;
    Py_ssize_t class_len;
} query_t;

static void free_query(query_t *query) {
    PyMem_Free(query->atoms);
    PyMem_Free(query->filters);
    PyMem_Free(query->class_ucs4);
}

static int resolve_axis(module_state *state, PyObject *value, enum th_axis *out) {
    for (int index = 0; index < 7; index++) {
        if (value == state->axes[index]) {
            *out = (enum th_axis)index;
            return 0;
        }
    }
    PyErr_SetString(PyExc_TypeError, "axis must be an Axis member");
    return -1;
}

/* Match one filter against a candidate value: a str (a tag name or attribute
   value), Py_None (a valueless attribute), or NULL (an absent attribute).
   Returns 1/0, or -1 with an exception set. */
static int filter_matches(module_state *state, PyObject *filter, PyObject *value) {
    if (PyBool_Check(filter)) {
        int present = value != NULL;
        return filter == Py_True ? present : !present;
    }
    if (PyList_Check(filter)) {
        Py_ssize_t count = PyList_GET_SIZE(filter);
        for (Py_ssize_t index = 0; index < count; index++) {
            int matched = filter_matches(state, PyList_GET_ITEM(filter, index), value);
            if (matched != 0) {
                return matched;
            }
        }
        return 0;
    }
    if (PyUnicode_Check(filter)) {
        if (value == NULL || value == Py_None) {
            return 0;
        }
        return PyUnicode_Compare(value, filter) == 0;
    }
    if (PyObject_TypeCheck(filter, (PyTypeObject *)state->pattern_type)) {
        if (value == NULL || value == Py_None) {
            return 0;
        }
        PyObject *match = PyObject_CallMethod(filter, "search", "O", value);
        if (match == NULL) { /* GCOVR_EXCL_BR_LINE: search over a str cannot raise */
            return -1;       /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        int matched = match != Py_None;
        Py_DECREF(match);
        return matched;
    }
    if (PyCallable_Check(filter)) {
        PyObject *result = PyObject_CallOneArg(filter, value != NULL ? value : Py_None);
        if (result == NULL) {
            return -1;
        }
        int truth = PyObject_IsTrue(result);
        Py_DECREF(result);
        return truth;
    }
    PyErr_SetString(PyExc_TypeError, "filter must be a str, bool, compiled regex, callable, or list");
    return -1;
}

/* The node's value for an attribute atom: a new str reference, Py_None for a
   valueless attribute (borrowed), or NULL when absent. *owned says whether the
   caller must DECREF (only the new-str case is owned). */
static PyObject *attr_value(th_node *node, uint32_t atom, int *owned) {
    *owned = 0;
    for (Py_ssize_t index = 0; index < node->attr_count; index++) {
        if (node->attrs[index].name_atom == atom) {
            const th_node_attr *attr = &node->attrs[index];
            if (attr->value == NULL) {
                return Py_None;
            }
            *owned = 1;
            return ucs4_to_str(attr->value, attr->value_len);
        }
    }
    return NULL;
}

/* class_ matches the multi-valued class attribute: against the whole value first,
   then each whitespace-separated token. */
static int class_matches(module_state *state, th_node *node, PyObject *filter) {
    const th_node_attr *attr = NULL;
    for (Py_ssize_t index = 0; index < node->attr_count; index++) {
        if (node->attrs[index].name_atom == TH_ATTR_CLASS) {
            attr = &node->attrs[index];
            break;
        }
    }
    if (attr == NULL || attr->value == NULL) {
        return filter_matches(state, filter, attr == NULL ? NULL : Py_None);
    }
    PyObject *whole = ucs4_to_str(attr->value, attr->value_len);
    if (whole == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;       /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    int matched = filter_matches(state, filter, whole);
    Py_DECREF(whole);
    if (matched != 0) {
        return matched;
    }
    Py_ssize_t cursor = 0;
    while (cursor < attr->value_len) {
        while (cursor < attr->value_len && is_space(attr->value[cursor])) {
            cursor++;
        }
        Py_ssize_t start = cursor;
        while (cursor < attr->value_len && !is_space(attr->value[cursor])) {
            cursor++;
        }
        if (cursor > start) {
            PyObject *token = ucs4_to_str(&attr->value[start], cursor - start);
            if (token == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
                return -1;       /* GCOVR_EXCL_LINE: allocation-failure path */
            }
            int token_matched = filter_matches(state, filter, token);
            Py_DECREF(token);
            if (token_matched != 0) {
                return token_matched;
            }
        }
    }
    return 0;
}

/* class_matches for a plain-string filter: compare the filter's code points to
   the whole class value and then each token directly, allocating nothing. */
static int class_matches_plain(th_node *node, const Py_UCS4 *want, Py_ssize_t want_len) {
    const th_node_attr *attr = NULL;
    for (Py_ssize_t index = 0; index < node->attr_count; index++) {
        if (node->attrs[index].name_atom == TH_ATTR_CLASS) {
            attr = &node->attrs[index];
            break;
        }
    }
    if (attr == NULL || attr->value == NULL) {
        return 0; /* a string filter never matches an absent or valueless class */
    }
    size_t bytes = (size_t)want_len * sizeof(Py_UCS4);
    if (attr->value_len == want_len && memcmp(attr->value, want, bytes) == 0) {
        return 1; /* the whole value equals the filter */
    }
    Py_ssize_t cursor = 0;
    while (cursor < attr->value_len) {
        while (cursor < attr->value_len && is_space(attr->value[cursor])) {
            cursor++;
        }
        Py_ssize_t start = cursor;
        while (cursor < attr->value_len && !is_space(attr->value[cursor])) {
            cursor++;
        }
        if (cursor - start == want_len && memcmp(&attr->value[start], want, bytes) == 0) {
            return 1;
        }
    }
    return 0;
}

/* Whether an element matches the whole query. Returns 1/0, or -1 with an
   exception set. */
static int node_matches(module_state *state, th_node *node, const query_t *query) {
    if (node->type != TH_NODE_ELEMENT) {
        return 0;
    }
    if (query->tag_plain) {
        /* a known name is a pure integer compare; an unknown one can only match
           the rare unknown-atom elements, compared by name */
        if (query->tag_atom != TH_TAG_UNKNOWN) {
            if (node->atom != query->tag_atom) {
                return 0;
            }
        } else {
            if (node->atom != TH_TAG_UNKNOWN) {
                return 0;
            }
            PyObject *name = ucs4_to_str(node->text, node->text_len);
            if (name == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
                return -1;      /* GCOVR_EXCL_LINE: allocation-failure path */
            }
            int equal = PyUnicode_Compare(name, query->tag) == 0;
            Py_DECREF(name);
            if (!equal) {
                return 0;
            }
        }
    } else if (query->tag != NULL) {
        PyObject *name = ucs4_to_str(node->text, node->text_len);
        if (name == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return -1;      /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        int matched = filter_matches(state, query->tag, name);
        Py_DECREF(name);
        if (matched <= 0) {
            return matched;
        }
    }
    if (query->class_ucs4 != NULL) {
        if (class_matches_plain(node, query->class_ucs4, query->class_len) == 0) {
            return 0;
        }
    } else if (query->class_filter != NULL) {
        int matched = class_matches(state, node, query->class_filter);
        if (matched <= 0) {
            return matched;
        }
    }
    for (Py_ssize_t index = 0; index < query->nattr; index++) {
        int owned;
        PyObject *value = attr_value(node, query->atoms[index], &owned);
        if (owned && value == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return -1;                /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        int matched = filter_matches(state, query->filters[index], value);
        if (owned) {
            Py_DECREF(value);
        }
        if (matched <= 0) {
            return matched;
        }
    }
    return 1;
}

static th_node *axis_first(th_node *node, enum th_axis axis) {
    switch (axis) {
    case TH_AXIS_ANCESTORS:
        return node->parent;
    case TH_AXIS_NEXT_SIBLINGS:
        return node->next_sibling;
    case TH_AXIS_PREVIOUS_SIBLINGS:
        return node->prev_sibling;
    case TH_AXIS_FOLLOWING:
        return subtree_next(node);
    case TH_AXIS_PRECEDING:
        return preceding_skip(previous_element(node), node);
    default: /* DESCENDANTS and CHILDREN both start at the first child */
        return node->first_child;
    }
}

static th_node *axis_next(th_node *current, th_node *origin, enum th_axis axis) {
    switch (axis) {
    case TH_AXIS_CHILDREN:
    case TH_AXIS_NEXT_SIBLINGS:
        return current->next_sibling;
    case TH_AXIS_PREVIOUS_SIBLINGS:
        return current->prev_sibling;
    case TH_AXIS_ANCESTORS:
        return current->parent;
    case TH_AXIS_FOLLOWING:
        return preorder_next(current, NULL);
    case TH_AXIS_PRECEDING:
        return preceding_skip(previous_element(current), origin);
    default: /* DESCENDANTS: pre-order, bounded to the origin's subtree */
        return preorder_next(current, origin);
    }
}

static int add_attr_filter(th_tree *tree, query_t *query, PyObject *key, PyObject *filter) {
    if (!PyUnicode_Check(key)) {
        PyErr_SetString(PyExc_TypeError, "attribute name must be a str");
        return -1;
    }
    Py_ssize_t len;
    const char *bytes = PyUnicode_AsUTF8AndSize(key, &len);
    if (bytes == NULL) { /* GCOVR_EXCL_BR_LINE: a str always encodes to UTF-8 */
        return -1;       /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    query->atoms[query->nattr] = th_attr_lookup(tree, bytes, len);
    query->filters[query->nattr] = filter;
    query->nattr++;
    return 0;
}

static int is_reserved_key(PyObject *key, int is_find_all) {
    return PyUnicode_CompareWithASCIIString(key, "axis") == 0 || PyUnicode_CompareWithASCIIString(key, "class_") == 0 ||
           PyUnicode_CompareWithASCIIString(key, "attrs") == 0 ||
           (is_find_all && PyUnicode_CompareWithASCIIString(key, "limit") == 0);
}

/* Compile the (tag, axis, class_, attrs, limit, **filters) arguments. Always
   leaves query in a free_query-safe state, even on error. */
static int build_query(PyObject *self, PyObject *args, PyObject *kwargs, int is_find_all, query_t *query) {
    module_state *state = state_of(self);
    th_tree *tree = tree_of(self);
    query->tag = NULL;
    query->class_filter = NULL;
    query->axis = TH_AXIS_DESCENDANTS;
    query->limit = -1;
    query->atoms = NULL;
    query->filters = NULL;
    query->nattr = 0;
    query->tag_plain = 0;
    query->tag_atom = TH_TAG_UNKNOWN;
    query->class_ucs4 = NULL;
    query->class_len = 0;

    PyObject *tag = NULL;
    if (!PyArg_ParseTuple(args, "|O:find", &tag)) {
        return -1;
    }
    if (tag != NULL && tag != Py_None) {
        query->tag = tag;
        /* a plain str tag matches by interned atom; encode case-sensitively (a
           find() name match is exact, unlike a case-insensitive CSS type) */
        if (PyUnicode_Check(tag)) {
            Py_ssize_t blen;
            const char *bytes = PyUnicode_AsUTF8AndSize(tag, &blen);
            if (bytes == NULL) {
                /* a lone surrogate cannot encode; fall back to the str-compare path */
                PyErr_Clear();
            } else {
                query->tag_plain = 1;
                query->tag_atom = blen > 0 ? th_tag_lookup(bytes, blen) : TH_TAG_UNKNOWN;
            }
        }
    }

    PyObject *attrs_dict = NULL;
    Py_ssize_t named = 0;
    PyObject *key, *value;
    Py_ssize_t pos = 0;
    while (kwargs != NULL && PyDict_Next(kwargs, &pos, &key, &value)) {
        if (PyUnicode_CompareWithASCIIString(key, "axis") == 0) {
            if (resolve_axis(state, value, &query->axis) < 0) {
                return -1;
            }
        } else if (PyUnicode_CompareWithASCIIString(key, "class_") == 0) {
            query->class_filter = value;
        } else if (PyUnicode_CompareWithASCIIString(key, "attrs") == 0) {
            if (!PyDict_Check(value)) {
                PyErr_SetString(PyExc_TypeError, "attrs must be a dict");
                return -1;
            }
            attrs_dict = value;
        } else if (is_find_all && PyUnicode_CompareWithASCIIString(key, "limit") == 0) {
            if (value == Py_None) {
                query->limit = -1;
            } else if (PyLong_Check(value)) {
                query->limit = PyLong_AsSsize_t(value);
                if (PyErr_Occurred()) { /* GCOVR_EXCL_BR_LINE: an overflowing limit cannot be forced from a test */
                    return -1;          /* GCOVR_EXCL_LINE: overflow path */
                }
            } else {
                PyErr_SetString(PyExc_TypeError, "limit must be an int or None");
                return -1;
            }
        } else {
            named++;
        }
    }

    if (query->class_filter != NULL && PyUnicode_Check(query->class_filter)) {
        /* a plain str class_ filter matches by code-point compare, no per-token str */
        query->class_len = PyUnicode_GET_LENGTH(query->class_filter);
        query->class_ucs4 = PyUnicode_AsUCS4Copy(query->class_filter);
        if (query->class_ucs4 == NULL) { /* GCOVR_EXCL_BR_LINE: allocation cannot be forced from a test */
            return -1;                   /* GCOVR_EXCL_LINE: allocation-failure path */
        }
    }

    Py_ssize_t capacity = named + (attrs_dict != NULL ? PyDict_GET_SIZE(attrs_dict) : 0);
    if (capacity > 0) {
        query->atoms = PyMem_Malloc((size_t)capacity * sizeof(uint32_t));
        query->filters = PyMem_Malloc((size_t)capacity * sizeof(PyObject *));
        if (query->atoms == NULL || query->filters == NULL) { /* GCOVR_EXCL_BR_LINE: allocation cannot be forced */
            return -1;                                        /* GCOVR_EXCL_LINE: allocation-failure path */
        }
    }
    pos = 0;
    while (kwargs != NULL && PyDict_Next(kwargs, &pos, &key, &value)) {
        if (is_reserved_key(key, is_find_all)) {
            continue;
        }
        if (add_attr_filter(tree, query, key, value) < 0) { /* GCOVR_EXCL_BR_LINE: a **kwargs key is always a str */
            return -1; /* GCOVR_EXCL_LINE: add_attr_filter only fails on a non-str name, impossible here */
        }
    }
    pos = 0;
    while (attrs_dict != NULL && PyDict_Next(attrs_dict, &pos, &key, &value)) {
        if (add_attr_filter(tree, query, key, value) < 0) {
            return -1;
        }
    }
    return 0;
}

static PyObject *node_find(PyObject *self, PyObject *args, PyObject *kwargs) {
    query_t query;
    if (build_query(self, args, kwargs, 0, &query) < 0) {
        free_query(&query);
        return NULL;
    }
    module_state *state = state_of(self);
    th_node *origin = ((NodeObject *)self)->node;
    th_node *found = NULL;
    int error = 0;
    for (th_node *node = axis_first(origin, query.axis); node != NULL; node = axis_next(node, origin, query.axis)) {
        int matched = node_matches(state, node, &query);
        if (matched < 0) {
            error = 1;
            break;
        }
        if (matched) {
            found = node;
            break;
        }
    }
    free_query(&query);
    if (error) {
        return NULL;
    }
    return node_wrap(state, ((NodeObject *)self)->handle, found);
}

static PyObject *node_find_all(PyObject *self, PyObject *args, PyObject *kwargs) {
    query_t query;
    if (build_query(self, args, kwargs, 1, &query) < 0) {
        free_query(&query);
        return NULL;
    }
    module_state *state = state_of(self);
    PyObject *handle = ((NodeObject *)self)->handle;
    th_node *origin = ((NodeObject *)self)->node;
    PyObject *out = PyList_New(0);
    if (out == NULL) {      /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        free_query(&query); /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;        /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    int error = 0;
    for (th_node *node = axis_first(origin, query.axis); node != NULL; node = axis_next(node, origin, query.axis)) {
        if (query.limit >= 0 && PyList_GET_SIZE(out) >= query.limit) {
            break;
        }
        int matched = node_matches(state, node, &query);
        if (matched < 0) {
            error = 1;
            break;
        }
        if (matched) {
            PyObject *wrapped = node_wrap(state, handle, node);
            /* allocation failure cannot be forced from a test */
            if (wrapped == NULL || PyList_Append(out, wrapped) < 0) { /* GCOVR_EXCL_BR_LINE */
                Py_XDECREF(wrapped);                                  /* GCOVR_EXCL_LINE: allocation-failure path */
                error = 1;                                            /* GCOVR_EXCL_LINE: allocation-failure path */
                break;                                                /* GCOVR_EXCL_LINE: allocation-failure path */
            }
            Py_DECREF(wrapped);
        }
    }
    free_query(&query);
    if (error) {
        Py_DECREF(out);
        return NULL;
    }
    return out;
}

static PyObject *node_select(PyObject *self, PyObject *arg) {
    if (!PyUnicode_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "selector must be a str");
        return NULL;
    }
    sel_compiled *compiled = selector_compile(tree_of(self), arg);
    if (compiled == NULL) {
        return NULL;
    }
    module_state *state = state_of(self);
    PyObject *handle = ((NodeObject *)self)->handle;
    th_node *origin = ((NodeObject *)self)->node;
    PyObject *out = PyList_New(0);
    if (out == NULL) {           /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        selector_free(compiled); /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;             /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    int error = 0;
    for (th_node *node = origin->first_child; node != NULL; node = preorder_next(node, origin)) {
        if (node->type != TH_NODE_ELEMENT || !selector_matches(node, compiled)) {
            continue;
        }
        PyObject *wrapped = node_wrap(state, handle, node);
        /* allocation failure cannot be forced from a test */
        if (wrapped == NULL || PyList_Append(out, wrapped) < 0) { /* GCOVR_EXCL_BR_LINE */
            Py_XDECREF(wrapped);                                  /* GCOVR_EXCL_LINE: allocation-failure path */
            error = 1;                                            /* GCOVR_EXCL_LINE: allocation-failure path */
            break;                                                /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        Py_DECREF(wrapped);
    }
    selector_free(compiled);
    if (error) {        /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        Py_DECREF(out); /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;    /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    return out;
}

static PyObject *node_select_one(PyObject *self, PyObject *arg) {
    if (!PyUnicode_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "selector must be a str");
        return NULL;
    }
    sel_compiled *compiled = selector_compile(tree_of(self), arg);
    if (compiled == NULL) {
        return NULL;
    }
    th_node *origin = ((NodeObject *)self)->node;
    th_node *found = NULL;
    for (th_node *node = origin->first_child; node != NULL; node = preorder_next(node, origin)) {
        if (node->type == TH_NODE_ELEMENT && selector_matches(node, compiled)) {
            found = node;
            break;
        }
    }
    selector_free(compiled);
    return node_wrap(state_of(self), ((NodeObject *)self)->handle, found);
}

static PyObject *node_css_matches(PyObject *self, PyObject *arg) {
    if (!PyUnicode_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "selector must be a str");
        return NULL;
    }
    sel_compiled *compiled = selector_compile(tree_of(self), arg);
    if (compiled == NULL) {
        return NULL;
    }
    th_node *node = ((NodeObject *)self)->node;
    int matched = node->type == TH_NODE_ELEMENT && selector_matches(node, compiled);
    selector_free(compiled);
    return PyBool_FromLong(matched);
}

static PyObject *node_css_closest(PyObject *self, PyObject *arg) {
    if (!PyUnicode_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "selector must be a str");
        return NULL;
    }
    sel_compiled *compiled = selector_compile(tree_of(self), arg);
    if (compiled == NULL) {
        return NULL;
    }
    th_node *found = NULL;
    for (th_node *node = ((NodeObject *)self)->node; node != NULL; node = node->parent) {
        if (node->type == TH_NODE_ELEMENT && selector_matches(node, compiled)) {
            found = node;
            break;
        }
    }
    selector_free(compiled);
    return node_wrap(state_of(self), ((NodeObject *)self)->handle, found);
}

/* Map a Formatter member to its enum th_formatter index; absent means the
   WHATWG default. */
static int resolve_formatter(module_state *state, PyObject *formatter, int *out) {
    if (formatter == NULL) {
        *out = 0;
        return 0;
    }
    for (int index = 0; index < 3; index++) {
        if (formatter == state->formatters[index]) {
            *out = index;
            return 0;
        }
    }
    PyErr_SetString(PyExc_TypeError, "formatter must be a Formatter member");
    return -1;
}

/* Resolve the indent argument to a per-level UCS4 unit: None for compact output,
   an int for that many spaces, or a string used verbatim. *out is a PyMem buffer
   the caller frees. */
static int resolve_indent(PyObject *indent, Py_UCS4 **out, Py_ssize_t *out_len) {
    *out = NULL;
    *out_len = 0;
    if (indent == NULL || indent == Py_None) {
        return 0;
    }
    if (PyLong_Check(indent)) {
        long count = PyLong_AsLong(indent);
        if (count == -1 && PyErr_Occurred()) { /* GCOVR_EXCL_BR_LINE: an int wider than long cannot be forced here */
            return -1;                         /* GCOVR_EXCL_LINE: overflow path */
        }
        if (count < 0) {
            PyErr_SetString(PyExc_ValueError, "indent must not be negative");
            return -1;
        }
        Py_UCS4 *buffer = PyMem_Malloc((count ? (size_t)count : 1) * sizeof(Py_UCS4));
        if (buffer == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
            return -1;        /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        for (long index = 0; index < count; index++) {
            buffer[index] = ' ';
        }
        *out = buffer;
        *out_len = count;
        return 0;
    }
    if (PyUnicode_Check(indent)) {
        *out_len = PyUnicode_GET_LENGTH(indent);
        *out = PyUnicode_AsUCS4Copy(indent);
        if (*out == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return -1;      /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        return 0;
    }
    PyErr_SetString(PyExc_TypeError, "indent must be an int, str, or None");
    return -1;
}

/* Serialize self to a str under the given Formatter member and indent argument. */
static PyObject *node_serialize_str(PyObject *self, PyObject *formatter_obj, PyObject *indent_obj) {
    int formatter;
    if (resolve_formatter(state_of(self), formatter_obj, &formatter) < 0) {
        return NULL;
    }
    Py_UCS4 *indent;
    Py_ssize_t indent_len;
    if (resolve_indent(indent_obj, &indent, &indent_len) < 0) {
        return NULL;
    }
    Py_ssize_t out_len;
    Py_UCS4 *data =
        th_node_serialize(tree_of(self), ((NodeObject *)self)->node, formatter, indent, indent_len, &out_len);
    PyMem_Free(indent);
    if (data == NULL) {          /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *result = ucs4_to_str(data, out_len);
    PyMem_Free(data);
    return result;
}

static PyObject *node_serialize(PyObject *self, PyObject *args, PyObject *kwds) {
    static char *keywords[] = {"formatter", "indent", NULL};
    PyObject *formatter_obj = NULL;
    PyObject *indent_obj = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|$OO", keywords, &formatter_obj, &indent_obj)) {
        return NULL;
    }
    return node_serialize_str(self, formatter_obj, indent_obj);
}

static PyObject *node_encode(PyObject *self, PyObject *args, PyObject *kwds) {
    static char *keywords[] = {"encoding", "formatter", "indent", NULL};
    const char *encoding = "utf-8";
    PyObject *formatter_obj = NULL;
    PyObject *indent_obj = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|s$OO", keywords, &encoding, &formatter_obj, &indent_obj)) {
        return NULL;
    }
    PyObject *text = node_serialize_str(self, formatter_obj, indent_obj);
    if (text == NULL) {
        return NULL;
    }
    PyObject *encoded = PyUnicode_AsEncodedString(text, encoding, NULL);
    Py_DECREF(text);
    return encoded;
}

PyDoc_STRVAR(element_doc, "An element node: a tag, a namespace, attributes, and child nodes.");

static PyType_Slot element_slots[] = {
    {Py_tp_doc, (void *)element_doc},
    {Py_tp_getset, element_getset},
    {0, NULL},
};

static PyType_Spec element_spec = {
    .name = "turbohtml._html.Element",
    .basicsize = sizeof(NodeObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION,
    .slots = element_slots,
};

/* ------------------------------------------- Text / Comment / Doctype --- */

static PyObject *node_get_data(PyObject *self, void *Py_UNUSED(closure)) {
    return str_from_accessor(th_node_data, tree_of(self), ((NodeObject *)self)->node);
}

static PyGetSetDef data_getset[] = {
    {"data", node_get_data, NULL, "the character data of this node", NULL},
    {NULL, NULL, NULL, NULL, NULL},
};

PyDoc_STRVAR(text_doc, "A run of character data.");

static PyType_Slot text_slots[] = {
    {Py_tp_doc, (void *)text_doc},
    {Py_tp_getset, data_getset},
    {0, NULL},
};

static PyType_Spec text_spec = {
    .name = "turbohtml._html.Text",
    .basicsize = sizeof(NodeObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION,
    .slots = text_slots,
};

PyDoc_STRVAR(comment_doc, "An HTML comment.");

static PyType_Slot comment_slots[] = {
    {Py_tp_doc, (void *)comment_doc},
    {Py_tp_getset, data_getset},
    {0, NULL},
};

static PyType_Spec comment_spec = {
    .name = "turbohtml._html.Comment",
    .basicsize = sizeof(NodeObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION,
    .slots = comment_slots,
};

static PyObject *doctype_get_name(PyObject *self, void *Py_UNUSED(closure)) {
    return str_from_accessor(th_node_data, tree_of(self), ((NodeObject *)self)->node);
}

static PyGetSetDef doctype_getset[] = {
    {"name", doctype_get_name, NULL, "the document type name", NULL},
    {NULL, NULL, NULL, NULL, NULL},
};

PyDoc_STRVAR(doctype_doc, "A document type declaration.");

static PyType_Slot doctype_slots[] = {
    {Py_tp_doc, (void *)doctype_doc},
    {Py_tp_getset, doctype_getset},
    {0, NULL},
};

static PyType_Spec doctype_spec = {
    .name = "turbohtml._html.Doctype",
    .basicsize = sizeof(NodeObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION,
    .slots = doctype_slots,
};

/* -------------------------------------------------------------- Document */

static PyObject *document_get_root(PyObject *self, void *Py_UNUSED(closure)) {
    NodeObject *node = (NodeObject *)self;
    /* a parsed document always has an html element child, so the loop never exhausts */
    th_node *child = node->node->first_child;
    /* allocation failure cannot be forced from a test */
    for (; child != NULL; child = child->next_sibling) { /* GCOVR_EXCL_BR_LINE */
        if (child->type == TH_NODE_ELEMENT) {
            return node_wrap(state_of(self), node->handle, child);
        }
    }
    Py_RETURN_NONE; /* GCOVR_EXCL_LINE: a parsed document always has an <html> element child */
}

static PyObject *document_get_encoding(PyObject *self, void *Py_UNUSED(closure)) {
    return Py_NewRef(((HandleObject *)((NodeObject *)self)->handle)->encoding);
}

static PyGetSetDef document_getset[] = {
    {"root", document_get_root, NULL, "the root <html> element, or None", NULL},
    {"encoding", document_get_encoding, NULL, "the resolved encoding name for bytes input, or None for str", NULL},
    {NULL, NULL, NULL, NULL, NULL},
};

PyDoc_STRVAR(document_doc, "A parsed document: the root of the tree returned by parse().");

static PyType_Slot document_slots[] = {
    {Py_tp_doc, (void *)document_doc},
    {Py_tp_getset, document_getset},
    {0, NULL},
};

static PyType_Spec document_spec = {
    .name = "turbohtml._html.Document",
    .basicsize = sizeof(NodeObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION,
    .slots = document_slots,
};

/* ----------------------------------------------------------- _TreeHandle */

static void handle_dealloc(PyObject *self) {
    PyTypeObject *type = Py_TYPE(self);
    HandleObject *handle = (HandleObject *)self;
    th_tree_free(handle->tree);
    Py_XDECREF(handle->source);
    Py_XDECREF(handle->encoding);
    type->tp_free(self);
    Py_DECREF(type);
}

static PyType_Slot handle_slots[] = {
    {Py_tp_dealloc, handle_dealloc},
    {0, NULL},
};

static PyType_Spec handle_spec = {
    .name = "turbohtml._html._TreeHandle",
    .basicsize = sizeof(HandleObject),
    .flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION,
    .slots = handle_slots,
};

static PyObject *handle_new(module_state *state, th_tree *tree, PyObject *source, PyObject *encoding) {
    PyTypeObject *type = (PyTypeObject *)state->handle_type;
    HandleObject *self = (HandleObject *)type->tp_alloc(type, 0);
    if (self == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;    /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    self->tree = tree;
    self->source = Py_NewRef(source);
    self->encoding = Py_NewRef(encoding);
    return (PyObject *)self;
}

/* ------------------------------------------------------- parse entrypoints */

/* Wrap a freshly built tree (which borrows source's storage) and return its
   document/context node. Frees the tree on wrapping failure. */
static PyObject *tree_to_node(module_state *state, th_tree *tree, PyObject *source, PyObject *encoding) {
    PyObject *handle = handle_new(state, tree, source, encoding);
    if (handle == NULL) {   /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        th_tree_free(tree); /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;        /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *node = node_wrap(state, handle, th_tree_document(tree));
    Py_DECREF(handle);
    return node;
}

/* Parse bytes: sniff the encoding (BOM, then the encoding argument, then a <meta>
   prescan, then windows-1252), decode with that codec replacing malformed bytes,
   and parse the resulting str. The decoded str is retained as the tree's source. */
static PyObject *parse_bytes(module_state *state, PyObject *markup, const char *enc_arg, Py_ssize_t enc_len) {
    Py_buffer view;
    if (PyObject_GetBuffer(markup, &view, PyBUF_SIMPLE) < 0) { /* GCOVR_EXCL_BR_LINE: bytes expose a simple buffer */
        return NULL;                                           /* GCOVR_EXCL_LINE: buffer-acquisition failure */
    }
    const unsigned char *bytes = view.buf;
    Py_ssize_t len = view.len;
    const th_encoding_entry *entry = NULL;
    Py_ssize_t skip = th_encoding_bom(bytes, len, &entry);
    if (entry == NULL && enc_arg != NULL) {
        entry = th_encoding_lookup(enc_arg, enc_len);
    }
    if (entry == NULL) {
        entry = th_encoding_prescan(bytes, len);
    }
    if (entry == NULL) {
        entry = th_encoding_lookup("windows-1252", 12);
    }
    PyObject *decoded = PyUnicode_Decode((const char *)bytes + skip, len - skip, entry->codec, "replace");
    PyBuffer_Release(&view);
    if (decoded == NULL) { /* GCOVR_EXCL_BR_LINE: the codec is from the table and the replace handler never fails */
        return NULL;       /* GCOVR_EXCL_LINE: decode failure */
    }
    th_tree *tree = th_tree_parse(PyUnicode_KIND(decoded), PyUnicode_DATA(decoded), PyUnicode_GET_LENGTH(decoded));
    if (tree == NULL) {          /* GCOVR_EXCL_BR_LINE: only an allocation failure returns NULL */
        Py_DECREF(decoded);      /* GCOVR_EXCL_LINE: allocation-failure path */
        return PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *canonical = PyUnicode_FromString(entry->canonical);
    if (canonical == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        th_tree_free(tree);  /* GCOVR_EXCL_LINE: allocation-failure path */
        Py_DECREF(decoded);  /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;         /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *node = tree_to_node(state, tree, decoded, canonical);
    Py_DECREF(canonical);
    Py_DECREF(decoded);
    return node;
}

PyObject *turbohtml_parse(PyObject *module, PyObject *args, PyObject *kwargs) {
    static char *keywords[] = {"markup", "encoding", NULL};
    PyObject *markup;
    const char *enc_arg = NULL;
    Py_ssize_t enc_len = 0;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|$z#:parse", keywords, &markup, &enc_arg, &enc_len)) {
        return NULL;
    }
    module_state *state = PyModule_GetState(module);
    if (PyUnicode_Check(markup)) {
        th_tree *tree = th_tree_parse(PyUnicode_KIND(markup), PyUnicode_DATA(markup), PyUnicode_GET_LENGTH(markup));
        if (tree == NULL) {          /* GCOVR_EXCL_BR_LINE: only an allocation failure returns NULL */
            return PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        return tree_to_node(state, tree, markup, Py_None);
    }
    if (!PyObject_CheckBuffer(markup)) {
        PyErr_SetString(PyExc_TypeError, "parse() argument must be str or a bytes-like object");
        return NULL;
    }
    return parse_bytes(state, markup, enc_arg, enc_len);
}

PyObject *turbohtml_tree_parse_fragment(PyObject *module, PyObject *args, PyObject *kwargs) {
    static char *keywords[] = {"html", "context", NULL};
    PyObject *text;
    const char *context = "div";
    Py_ssize_t context_len = 3;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "U|s#:parse_fragment", keywords, &text, &context, &context_len)) {
        return NULL;
    }
    th_tree *tree = th_tree_parse_fragment(PyUnicode_KIND(text), PyUnicode_DATA(text), PyUnicode_GET_LENGTH(text),
                                           context, context_len);
    if (tree == NULL) {          /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    return tree_to_node(PyModule_GetState(module), tree, text, Py_None);
}

/* ----------------------------------------------------------- registration */

static int build_namespace_enum(PyObject *module, module_state *state) {
    static const char *const names[3] = {"HTML", "SVG", "MATHML"};
    static const char *const values[3] = {"html", "svg", "math"};
    PyObject *members = PyDict_New();
    if (members == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;         /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    for (int index = 0; index < 3; index++) {
        PyObject *value = PyUnicode_FromString(values[index]);
        /* allocation failure cannot be forced from a test */
        if (value == NULL || PyDict_SetItemString(members, names[index], value) < 0) { /* GCOVR_EXCL_BR_LINE */
            Py_XDECREF(value);  /* GCOVR_EXCL_LINE: alloc-failure path */
            Py_DECREF(members); /* GCOVR_EXCL_LINE: alloc-failure path */
            return -1;          /* GCOVR_EXCL_LINE: alloc-failure path */
        }
        Py_DECREF(value);
    }
    PyObject *enum_module = PyImport_ImportModule("enum");
    if (enum_module == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        Py_DECREF(members);    /* GCOVR_EXCL_LINE: allocation-failure path */
        return -1;             /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *enum_type = PyObject_GetAttrString(enum_module, "Enum");
    Py_DECREF(enum_module);
    if (enum_type == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        Py_DECREF(members);  /* GCOVR_EXCL_LINE: allocation-failure path */
        return -1;           /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *args = Py_BuildValue("(sO)", "Namespace", members);
    Py_DECREF(members);
    PyObject *kwargs = Py_BuildValue("{s:s,s:s}", "module", "turbohtml", "qualname", "Namespace");
    PyObject *namespace_enum = NULL;
    if (args != NULL && kwargs != NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        namespace_enum = PyObject_Call(enum_type, args, kwargs);
    }
    Py_DECREF(enum_type);
    Py_XDECREF(args);
    Py_XDECREF(kwargs);
    if (namespace_enum == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;                /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    for (int slot = 0; slot < 3; slot++) {
        state->namespaces[slot] = PyObject_GetAttrString(namespace_enum, names[slot]);
        if (state->namespaces[slot] == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            Py_DECREF(namespace_enum);         /* GCOVR_EXCL_LINE: allocation-failure path */
            return -1;                         /* GCOVR_EXCL_LINE: allocation-failure path */
        }
    }
    state->namespace_enum = namespace_enum;
    return PyModule_AddObjectRef(module, "Namespace", namespace_enum);
}

static int build_axis_enum(PyObject *module, module_state *state) {
    static const char *const names[7] = {"DESCENDANTS",       "CHILDREN",  "ANCESTORS", "NEXT_SIBLINGS",
                                         "PREVIOUS_SIBLINGS", "FOLLOWING", "PRECEDING"};
    PyObject *members = PyDict_New();
    if (members == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;         /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    for (int index = 0; index < 7; index++) {
        PyObject *value = PyLong_FromLong(index);
        /* allocation failure cannot be forced from a test */
        if (value == NULL || PyDict_SetItemString(members, names[index], value) < 0) { /* GCOVR_EXCL_BR_LINE */
            Py_XDECREF(value);  /* GCOVR_EXCL_LINE: alloc-failure path */
            Py_DECREF(members); /* GCOVR_EXCL_LINE: alloc-failure path */
            return -1;          /* GCOVR_EXCL_LINE: alloc-failure path */
        }
        Py_DECREF(value);
    }
    PyObject *enum_module = PyImport_ImportModule("enum");
    if (enum_module == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        Py_DECREF(members);    /* GCOVR_EXCL_LINE: allocation-failure path */
        return -1;             /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *enum_type = PyObject_GetAttrString(enum_module, "IntEnum");
    Py_DECREF(enum_module);
    if (enum_type == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        Py_DECREF(members);  /* GCOVR_EXCL_LINE: allocation-failure path */
        return -1;           /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *args = Py_BuildValue("(sO)", "Axis", members);
    Py_DECREF(members);
    PyObject *kwargs = Py_BuildValue("{s:s,s:s}", "module", "turbohtml", "qualname", "Axis");
    PyObject *axis_enum = NULL;
    if (args != NULL && kwargs != NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        axis_enum = PyObject_Call(enum_type, args, kwargs);
    }
    Py_DECREF(enum_type);
    Py_XDECREF(args);
    Py_XDECREF(kwargs);
    if (axis_enum == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;           /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    for (int index = 0; index < 7; index++) {
        state->axes[index] = PyObject_GetAttrString(axis_enum, names[index]);
        if (state->axes[index] == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            Py_DECREF(axis_enum);         /* GCOVR_EXCL_LINE: allocation-failure path */
            return -1;                    /* GCOVR_EXCL_LINE: allocation-failure path */
        }
    }
    state->axis_enum = axis_enum;
    return PyModule_AddObjectRef(module, "Axis", axis_enum);
}

static int build_formatter_enum(PyObject *module, module_state *state) {
    static const char *const names[3] = {"WHATWG", "MINIMAL", "NAMED_ENTITIES"};
    static const char *const values[3] = {"whatwg", "minimal", "named"};
    PyObject *members = PyDict_New();
    if (members == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;         /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    for (int index = 0; index < 3; index++) {
        PyObject *value = PyUnicode_FromString(values[index]);
        /* allocation failure cannot be forced from a test */
        if (value == NULL || PyDict_SetItemString(members, names[index], value) < 0) { /* GCOVR_EXCL_BR_LINE */
            Py_XDECREF(value);  /* GCOVR_EXCL_LINE: alloc-failure path */
            Py_DECREF(members); /* GCOVR_EXCL_LINE: alloc-failure path */
            return -1;          /* GCOVR_EXCL_LINE: alloc-failure path */
        }
        Py_DECREF(value);
    }
    PyObject *enum_module = PyImport_ImportModule("enum");
    if (enum_module == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        Py_DECREF(members);    /* GCOVR_EXCL_LINE: allocation-failure path */
        return -1;             /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *enum_type = PyObject_GetAttrString(enum_module, "Enum");
    Py_DECREF(enum_module);
    if (enum_type == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        Py_DECREF(members);  /* GCOVR_EXCL_LINE: allocation-failure path */
        return -1;           /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *args = Py_BuildValue("(sO)", "Formatter", members);
    Py_DECREF(members);
    PyObject *kwargs = Py_BuildValue("{s:s,s:s}", "module", "turbohtml", "qualname", "Formatter");
    PyObject *formatter_enum = NULL;
    if (args != NULL && kwargs != NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        formatter_enum = PyObject_Call(enum_type, args, kwargs);
    }
    Py_DECREF(enum_type);
    Py_XDECREF(args);
    Py_XDECREF(kwargs);
    if (formatter_enum == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;                /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    for (int index = 0; index < 3; index++) {
        state->formatters[index] = PyObject_GetAttrString(formatter_enum, names[index]);
        if (state->formatters[index] == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
            Py_DECREF(formatter_enum);          /* GCOVR_EXCL_LINE: allocation-failure path */
            return -1;                          /* GCOVR_EXCL_LINE: allocation-failure path */
        }
    }
    state->formatter_enum = formatter_enum;
    return PyModule_AddObjectRef(module, "Formatter", formatter_enum);
}

static int cache_pattern_type(module_state *state) {
    PyObject *re_module = PyImport_ImportModule("re");
    if (re_module == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;           /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    state->pattern_type = PyObject_GetAttrString(re_module, "Pattern");
    Py_DECREF(re_module);
    if (state->pattern_type == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;                     /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    return 0;
}

/* Create a heap type subclassing Node, register it on the module, and (when
   match_args is given) stamp its __match_args__ for structural pattern use. */
static PyObject *register_subtype(PyObject *module, PyType_Spec *spec, PyObject *base, const char *name,
                                  const char *match_args) {
    PyObject *bases = PyTuple_Pack(1, base);
    if (bases == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;     /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *type = PyType_FromModuleAndSpec(module, spec, bases);
    Py_DECREF(bases);
    if (type == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;    /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    if (match_args != NULL) {
        PyObject *tuple = Py_BuildValue("(s)", match_args);
        /* allocation failure cannot be forced from a test */
        if (tuple == NULL || PyObject_SetAttrString(type, "__match_args__", tuple) < 0) { /* GCOVR_EXCL_BR_LINE */
            Py_XDECREF(tuple); /* GCOVR_EXCL_LINE: alloc-failure path */
            Py_DECREF(type);   /* GCOVR_EXCL_LINE: alloc-failure path */
            return NULL;       /* GCOVR_EXCL_LINE: alloc-failure path */
        }
        Py_DECREF(tuple);
    }
    /* allocation failure cannot be forced from a test */
    if (PyModule_AddObjectRef(module, name, type) < 0) { /* GCOVR_EXCL_BR_LINE */
        Py_DECREF(type);                                 /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;                                     /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    return type;
}

int tree_register(PyObject *module, module_state *state) {
    /* allocation failure cannot be forced from a test */
    if (build_namespace_enum(module, state) < 0) { /* GCOVR_EXCL_BR_LINE */
        return -1;                                 /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    if (build_axis_enum(module, state) < 0) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        return -1;                            /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    if (build_formatter_enum(module, state) < 0) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        return -1;                                 /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    if (cache_pattern_type(state) < 0) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        return -1;                       /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    state->walker_type = PyType_FromModuleAndSpec(module, &walker_spec, NULL);
    state->string_walker_type = PyType_FromModuleAndSpec(module, &string_walker_spec, NULL);
    state->handle_type = PyType_FromModuleAndSpec(module, &handle_spec, NULL);
    /* allocation failure cannot be forced from a test */
    if (state->walker_type == NULL || state->string_walker_type == NULL || /* GCOVR_EXCL_BR_LINE */
        state->handle_type == NULL) {                                      /* GCOVR_EXCL_BR_LINE */
        return -1; /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    state->node_type = PyType_FromModuleAndSpec(module, &node_spec, NULL);
    if (state->node_type == NULL || PyModule_AddObjectRef(module, "Node", state->node_type) < 0) { /* GCOVR_EXCL_BR_LINE
                                                                                                    */
        return -1; /* GCOVR_EXCL_LINE: alloc-failure path */
    }
    state->element_type = register_subtype(module, &element_spec, state->node_type, "Element", "tag");
    state->text_type = register_subtype(module, &text_spec, state->node_type, "Text", "data");
    state->comment_type = register_subtype(module, &comment_spec, state->node_type, "Comment", "data");
    state->doctype_type = register_subtype(module, &doctype_spec, state->node_type, "Doctype", "name");
    state->document_type = register_subtype(module, &document_spec, state->node_type, "Document", NULL);
    /* allocation failure cannot be forced from a test */
    if (state->element_type == NULL || state->text_type == NULL || /* GCOVR_EXCL_BR_LINE */
        /* allocation failure cannot be forced from a test */
        state->comment_type == NULL || state->doctype_type == NULL || /* GCOVR_EXCL_BR_LINE */
        /* allocation failure cannot be forced from a test */
        state->document_type == NULL) { /* GCOVR_EXCL_BR_LINE */
        return -1;                      /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    return 0;
}
