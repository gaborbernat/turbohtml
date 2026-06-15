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
#include "treebuilder.h"

typedef struct {
    PyObject_HEAD th_tree *tree;
    PyObject *source; /* the input str whose storage the tree's spans borrow */
} HandleObject;

typedef struct {
    PyObject_HEAD PyObject *handle; /* _TreeHandle keeping tree + source alive */
    th_node *node;
} NodeObject;

enum walk_mode { WALK_DESCENDANTS, WALK_ANCESTORS };

typedef struct {
    PyObject_HEAD PyObject *handle;
    th_node *root;    /* subtree bound for pre-order walks (unused for ancestors) */
    th_node *current; /* next node to yield, or NULL when exhausted */
    int mode;
} WalkerObject;

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
    walker->current = walker->mode == WALK_ANCESTORS ? node->parent : preorder_next(node, walker->root);
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

static PyObject *node_get_text(PyObject *self, void *Py_UNUSED(closure)) {
    return str_from_accessor(th_node_text, tree_of(self), ((NodeObject *)self)->node);
}

static PyObject *node_get_html(PyObject *self, void *Py_UNUSED(closure)) {
    return str_from_accessor(th_node_html, tree_of(self), ((NodeObject *)self)->node);
}

static PyGetSetDef node_getset[] = {
    {"parent", node_get_parent, NULL, "the parent Element or Document, or None for the document root", NULL},
    {"children", node_get_children, NULL, "the child nodes as a tuple", NULL},
    {"next_sibling", node_get_next_sibling, NULL, "the following sibling node, or None", NULL},
    {"previous_sibling", node_get_previous_sibling, NULL, "the preceding sibling node, or None", NULL},
    {"descendants", node_get_descendants, NULL, "an iterator over every descendant in document order", NULL},
    {"ancestors", node_get_ancestors, NULL, "an iterator from parent up to the document", NULL},
    {"text", node_get_text, NULL, "the concatenated character data of every Text descendant", NULL},
    {"html", node_get_html, NULL, "the HTML serialization of this node and its subtree", NULL},
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

PyDoc_STRVAR(find_doc, "find(tag=None, /, **attrs)\n--\n\n"
                       "Return the first descendant Element matching tag and every attribute in\n"
                       "attrs, in document order, or None if there is no match.");

PyDoc_STRVAR(find_all_doc, "find_all(tag=None, /, **attrs)\n--\n\n"
                           "Iterate, in document order, over every descendant Element matching tag\n"
                           "and every attribute in attrs.");

static PyMethodDef node_methods[] = {
    {"find", (PyCFunction)(void (*)(void))node_find, METH_VARARGS | METH_KEYWORDS, find_doc},
    {"find_all", (PyCFunction)(void (*)(void))node_find_all, METH_VARARGS | METH_KEYWORDS, find_all_doc},
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
   name, not by element; invalid markup such as <div rel> is the only case where
   that differs from a tag-specific table. */
static int attr_is_token_list(const char *name, Py_ssize_t name_len) {
    switch (name_len) {
    case 3:
        return memcmp(name, "rel", 3) == 0 || memcmp(name, "rev", 3) == 0;
    case 5:
        return memcmp(name, "class", 5) == 0 || memcmp(name, "sizes", 5) == 0;
    case 7:
        return memcmp(name, "headers", 7) == 0 || memcmp(name, "sandbox", 7) == 0 || memcmp(name, "archive", 7) == 0;
    case 8:
        return memcmp(name, "dropzone", 8) == 0;
    case 9:
        return memcmp(name, "accesskey", 9) == 0;
    case 14:
        return memcmp(name, "accept-charset", 14) == 0;
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

/* Build the attribute mapping. With split set, token-list attributes (class and
   friends) become a list[str]; element_matches passes 0 to keep find()'s exact
   whole-string comparison. A valueless attribute is always None. */
static PyObject *build_attrs(const th_node *node, int split) {
    PyObject *attrs = PyDict_New();
    if (attrs == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;     /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    for (Py_ssize_t attr_index = 0; attr_index < node->attr_count; attr_index++) {
        const th_node_attr *attr = &node->attrs[attr_index];
        PyObject *name = PyUnicode_DecodeUTF8(attr->name, attr->name_len, "strict");
        PyObject *value;
        if (attr->value == NULL) {
            value = Py_NewRef(Py_None);
        } else if (split && attr_is_token_list(attr->name, attr->name_len)) {
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
    return build_attrs(((NodeObject *)self)->node, 1);
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

/* Whether node matches the optional tag (a str or NULL) and every name=value in
   the optional attrs dict. Returns 1/0, or -1 with an exception set. */
static int element_matches(th_node *node, PyObject *tag, PyObject *attrs) {
    if (node->type != TH_NODE_ELEMENT) {
        return 0;
    }
    if (tag != NULL) {
        PyObject *name = ucs4_to_str(node->text, node->text_len);
        if (name == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return -1;      /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        int cmp = PyUnicode_Compare(name, tag);
        Py_DECREF(name);
        if (cmp != 0) {
            return 0;
        }
    }
    if (attrs == NULL || PyDict_GET_SIZE(attrs) == 0) {
        return 1;
    }
    PyObject *have = build_attrs(node, 0);
    if (have == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;      /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *key, *want;
    Py_ssize_t pos = 0;
    int matched = 1;
    while (matched && PyDict_Next(attrs, &pos, &key, &want)) {
        /* keys come from **attrs, so they are always hashable strs and the
           borrowed lookup never errors; a miss means no match */
        PyObject *got = PyDict_GetItem(have, key);
        if (got == NULL) {
            matched = 0;
            break;
        }
        int equal = PyObject_RichCompareBool(got, want, Py_EQ);
        if (equal <= 0) {
            matched = equal < 0 ? -1 : 0; /* GCOVR_EXCL_BR_LINE: str/None comparison cannot raise */
        }
    }
    Py_DECREF(have);
    return matched;
}

static th_node *find_first(th_node *node, PyObject *tag, PyObject *attrs, int *error) {
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        int matched = element_matches(child, tag, attrs);
        if (matched < 0) { /* GCOVR_EXCL_BR_LINE: matching fails only on an allocation error */
            *error = 1;    /* GCOVR_EXCL_LINE: matching fails only on an allocation error */
            return NULL;   /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        if (matched) {
            return child;
        }
        th_node *deeper = find_first(child, tag, attrs, error);
        if (deeper != NULL || *error) { /* GCOVR_EXCL_BR_LINE: *error is set only on an allocation failure */
            return deeper;
        }
    }
    return NULL;
}

static int collect_matches(module_state *state, PyObject *handle, th_node *node, PyObject *tag, PyObject *attrs,
                           PyObject *out) {
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        int matched = element_matches(child, tag, attrs);
        if (matched < 0) { /* GCOVR_EXCL_BR_LINE: matching fails only on an allocation error */
            return -1;     /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        if (matched) {
            PyObject *wrapped = node_wrap(state, handle, child);
            /* allocation failure cannot be forced from a test */
            if (wrapped == NULL || PyList_Append(out, wrapped) < 0) { /* GCOVR_EXCL_BR_LINE */
                Py_XDECREF(wrapped);                                  /* GCOVR_EXCL_LINE: allocation-failure path */
                return -1;                                            /* GCOVR_EXCL_LINE: allocation-failure path */
            }
            Py_DECREF(wrapped);
        }
        /* allocation failure cannot be forced from a test */
        if (collect_matches(state, handle, child, tag, attrs, out) < 0) { /* GCOVR_EXCL_BR_LINE */
            return -1;                                                    /* GCOVR_EXCL_LINE: allocation-failure path */
        }
    }
    return 0;
}

/* Validate the shared (tag, **attrs) query arguments of find/find_all. */
static int parse_query(PyObject *args, PyObject **tag) {
    *tag = NULL;
    if (!PyArg_ParseTuple(args, "|O", tag)) {
        return -1;
    }
    if (*tag == Py_None) {
        *tag = NULL;
    } else if (*tag != NULL && !PyUnicode_Check(*tag)) {
        PyErr_SetString(PyExc_TypeError, "tag must be a str or None");
        return -1;
    }
    return 0;
}

static PyObject *node_find(PyObject *self, PyObject *args, PyObject *kwargs) {
    PyObject *tag;
    if (parse_query(args, &tag) < 0) {
        return NULL;
    }
    NodeObject *node = (NodeObject *)self;
    int error = 0;
    th_node *match = find_first(node->node, tag, kwargs, &error);
    if (error) {     /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL; /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    return node_wrap(state_of(self), node->handle, match);
}

static PyObject *node_find_all(PyObject *self, PyObject *args, PyObject *kwargs) {
    PyObject *tag;
    if (parse_query(args, &tag) < 0) {
        return NULL;
    }
    NodeObject *node = (NodeObject *)self;
    PyObject *matches = PyList_New(0);
    if (matches == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;       /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    /* allocation failure cannot be forced from a test */
    if (collect_matches(state_of(self), node->handle, node->node, tag, kwargs, matches) < 0) { /* GCOVR_EXCL_BR_LINE */
        Py_DECREF(matches); /* GCOVR_EXCL_LINE: alloc-failure path */
        return NULL;        /* GCOVR_EXCL_LINE: alloc-failure path */
    }
    PyObject *iterator = PyObject_GetIter(matches);
    Py_DECREF(matches);
    return iterator;
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

static PyGetSetDef document_getset[] = {
    {"root", document_get_root, NULL, "the root <html> element, or None", NULL},
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

static PyObject *handle_new(module_state *state, th_tree *tree, PyObject *source) {
    PyTypeObject *type = (PyTypeObject *)state->handle_type;
    HandleObject *self = (HandleObject *)type->tp_alloc(type, 0);
    if (self == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;    /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    self->tree = tree;
    self->source = Py_NewRef(source);
    return (PyObject *)self;
}

/* ------------------------------------------------------- parse entrypoints */

/* Wrap a freshly built tree (which borrows source's storage) and return its
   document/context node. Frees the tree on wrapping failure. */
static PyObject *tree_to_node(module_state *state, th_tree *tree, PyObject *source) {
    PyObject *handle = handle_new(state, tree, source);
    if (handle == NULL) {   /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        th_tree_free(tree); /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;        /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    PyObject *node = node_wrap(state, handle, th_tree_document(tree));
    Py_DECREF(handle);
    return node;
}

PyObject *turbohtml_parse(PyObject *module, PyObject *arg) {
    if (!PyUnicode_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "parse() argument must be str");
        return NULL;
    }
    th_tree *tree = th_tree_parse(PyUnicode_KIND(arg), PyUnicode_DATA(arg), PyUnicode_GET_LENGTH(arg));
    if (tree == NULL) {          /* GCOVR_EXCL_BR_LINE: only an allocation failure returns NULL */
        return PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    return tree_to_node(PyModule_GetState(module), tree, arg);
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
    return tree_to_node(PyModule_GetState(module), tree, text);
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
    state->walker_type = PyType_FromModuleAndSpec(module, &walker_spec, NULL);
    state->handle_type = PyType_FromModuleAndSpec(module, &handle_spec, NULL);
    /* allocation failure cannot be forced from a test */
    if (state->walker_type == NULL || state->handle_type == NULL) { /* GCOVR_EXCL_BR_LINE */
        return -1;                                                  /* GCOVR_EXCL_LINE: allocation-failure path */
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
