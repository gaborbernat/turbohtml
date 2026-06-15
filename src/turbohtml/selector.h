/* A CSS selector engine over the node tree, #included into tree_type.c. A
   selector is compiled against the tree it will run on, so tag and attribute
   names resolve to interned atoms once and every match is an integer compare.
   Matching is right-to-left with backtracking on the descendant and general
   sibling combinators. This covers the common subset: type, universal, class,
   id, attribute operators, and the four combinators, grouped by commas. */

#ifndef TURBOHTML_SELECTOR_H
#define TURBOHTML_SELECTOR_H

#include "ascii.h"
#include "treebuilder.h"

enum sel_attr_op { OP_EXISTS, OP_EQ, OP_INCLUDE, OP_DASH, OP_PREFIX, OP_SUFFIX, OP_SUBSTR };

typedef struct {
    char kind;          /* '*', 'e' type, '.' class, '#' id, '[' attribute */
    uint16_t tag_atom;  /* 'e': the tag atom, TH_TAG_UNKNOWN for a name outside the table */
    uint32_t attr_atom; /* '[': the attribute atom, UINT32_MAX when no element has the name */
    enum sel_attr_op op;
    int ci;                 /* '[': matched case-insensitively */
    const Py_UCS4 *name;    /* class / id / unknown tag name (into the owned source copy) */
    Py_ssize_t name_len;    /* also the attribute name for the rare unknown case */
    const Py_UCS4 *value;   /* '[': the attribute value */
    Py_ssize_t value_len;
} sel_simple;

typedef struct {
    sel_simple *simples;
    int count;
    char combinator; /* ' ', '>', '+', '~': the combinator joining the compound on the left */
} sel_compound;

typedef struct {
    sel_compound *compounds; /* left to right; matched from the rightmost (the subject) */
    int count;
} sel_complex;

typedef struct {
    Py_UCS4 *source; /* an owned copy of the selector text the slices point into */
    sel_complex *alts;
    int count;
    int failed; /* an allocation or a syntax error happened during compile */
} sel_compiled;

/* ---------------------------------------------------------------- parsing */

typedef struct {
    const Py_UCS4 *src;
    Py_ssize_t pos;
    Py_ssize_t len;
    th_tree *tree;
    int error;
} sel_parser;

static int sel_is_ident(Py_UCS4 ch) {
    return is_ascii_alpha(ch) || (ch >= '0' && ch <= '9') || ch == '-' || ch == '_' || ch >= 0x80;
}

static void sel_skip_ws(sel_parser *parser) {
    while (parser->pos < parser->len && is_space(parser->src[parser->pos])) {
        parser->pos++;
    }
}

/* Read an identifier run, returning its slice via *out / *out_len. */
static void sel_ident(sel_parser *parser, const Py_UCS4 **out, Py_ssize_t *out_len) {
    Py_ssize_t start = parser->pos;
    while (parser->pos < parser->len && sel_is_ident(parser->src[parser->pos])) {
        parser->pos++;
    }
    *out = parser->src + start;
    *out_len = parser->pos - start;
    if (*out_len == 0) {
        parser->error = 1;
    }
}

/* UTF-8 encode a slice and resolve it to a tag atom. */
static uint16_t sel_tag_atom(const Py_UCS4 *name, Py_ssize_t len) {
    char bytes[64];
    Py_ssize_t at = 0;
    for (Py_ssize_t index = 0; index < len && at < (Py_ssize_t)sizeof(bytes) - 4; index++) {
        Py_UCS4 ch = name[index];
        if (ch >= 'A' && ch <= 'Z') {
            ch += 32; /* tag names match case-insensitively */
        }
        if (ch < 0x80) {
            bytes[at++] = (char)ch;
        } else {
            bytes[at++] = '\x01'; /* a non-ASCII byte is never in the tag table */
        }
    }
    return th_tag_lookup(bytes, at);
}

static uint32_t sel_attr_atom(th_tree *tree, const Py_UCS4 *name, Py_ssize_t len) {
    char bytes[128];
    Py_ssize_t at = 0;
    for (Py_ssize_t index = 0; index < len && at < (Py_ssize_t)sizeof(bytes) - 4; index++) {
        Py_UCS4 ch = name[index];
        if (ch >= 'A' && ch <= 'Z') {
            ch += 32; /* attribute names are lowercased in the tree */
        }
        if (ch < 0x80) {
            bytes[at++] = (char)ch;
        } else if (ch < 0x800) {
            bytes[at++] = (char)(0xC0 | (ch >> 6));
            bytes[at++] = (char)(0x80 | (ch & 0x3F));
        } else if (ch < 0x10000) {
            bytes[at++] = (char)(0xE0 | (ch >> 12));
            bytes[at++] = (char)(0x80 | ((ch >> 6) & 0x3F));
            bytes[at++] = (char)(0x80 | (ch & 0x3F));
        } else {
            bytes[at++] = (char)(0xF0 | (ch >> 18));
            bytes[at++] = (char)(0x80 | ((ch >> 12) & 0x3F));
            bytes[at++] = (char)(0x80 | ((ch >> 6) & 0x3F));
            bytes[at++] = (char)(0x80 | (ch & 0x3F));
        }
    }
    return th_attr_lookup(tree, bytes, at);
}

/* Parse a bracketed attribute selector (the leading '[' already consumed). */
static void sel_attribute(sel_parser *parser, sel_simple *simple) {
    simple->kind = '[';
    simple->op = OP_EXISTS;
    sel_skip_ws(parser);
    const Py_UCS4 *name;
    Py_ssize_t name_len;
    sel_ident(parser, &name, &name_len);
    if (parser->error) {
        return;
    }
    simple->attr_atom = sel_attr_atom(parser->tree, name, name_len);
    sel_skip_ws(parser);
    Py_UCS4 ch = parser->pos < parser->len ? parser->src[parser->pos] : 0;
    if (ch == ']') {
        parser->pos++;
        return;
    }
    if (ch == '~' || ch == '|' || ch == '^' || ch == '$' || ch == '*') {
        simple->op = ch == '~'   ? OP_INCLUDE
                     : ch == '|' ? OP_DASH
                     : ch == '^' ? OP_PREFIX
                     : ch == '$' ? OP_SUFFIX
                                 : OP_SUBSTR;
        parser->pos++;
        if (parser->pos >= parser->len || parser->src[parser->pos] != '=') {
            parser->error = 1;
            return;
        }
        parser->pos++;
    } else if (ch == '=') {
        simple->op = OP_EQ;
        parser->pos++;
    } else {
        parser->error = 1;
        return;
    }
    sel_skip_ws(parser);
    if (parser->pos < parser->len && (parser->src[parser->pos] == '"' || parser->src[parser->pos] == '\'')) {
        Py_UCS4 quote = parser->src[parser->pos++];
        Py_ssize_t start = parser->pos;
        while (parser->pos < parser->len && parser->src[parser->pos] != quote) {
            parser->pos++;
        }
        if (parser->pos >= parser->len) {
            parser->error = 1;
            return;
        }
        simple->value = parser->src + start;
        simple->value_len = parser->pos - start;
        parser->pos++;
    } else {
        sel_ident(parser, &simple->value, &simple->value_len);
        if (parser->error) {
            return;
        }
    }
    sel_skip_ws(parser);
    if (parser->pos < parser->len && (parser->src[parser->pos] | 32) == 'i') {
        simple->ci = 1;
        parser->pos++;
        sel_skip_ws(parser);
    } else if (parser->pos < parser->len && (parser->src[parser->pos] | 32) == 's') {
        parser->pos++;
        sel_skip_ws(parser);
    }
    if (parser->pos >= parser->len || parser->src[parser->pos] != ']') {
        parser->error = 1;
        return;
    }
    parser->pos++;
}

/* Parse one simple selector into *simple. */
static void sel_one(sel_parser *parser, sel_simple *simple) {
    simple->tag_atom = TH_TAG_UNKNOWN;
    simple->attr_atom = 0;
    simple->ci = 0;
    simple->name = NULL;
    simple->name_len = 0;
    simple->value = NULL;
    simple->value_len = 0;
    Py_UCS4 ch = parser->src[parser->pos];
    if (ch == '*') {
        simple->kind = '*';
        parser->pos++;
    } else if (ch == '.' || ch == '#') {
        simple->kind = (char)ch;
        parser->pos++;
        sel_ident(parser, &simple->name, &simple->name_len);
    } else if (ch == '[') {
        parser->pos++;
        sel_attribute(parser, simple);
    } else {
        /* an identifier: sel_starts_simple guarantees at least one char, so
           sel_ident here always succeeds */
        simple->kind = 'e';
        sel_ident(parser, &simple->name, &simple->name_len);
        simple->tag_atom = sel_tag_atom(simple->name, simple->name_len);
    }
}

static int sel_starts_simple(Py_UCS4 ch) {
    return ch == '*' || ch == '.' || ch == '#' || ch == '[' || sel_is_ident(ch);
}

/* Parse a compound (one or more adjacent simples) into the given buffer. */
static int sel_compound_parse(sel_parser *parser, sel_simple *buffer, int capacity) {
    int count = 0;
    while (parser->pos < parser->len && sel_starts_simple(parser->src[parser->pos])) {
        if (count >= capacity) {
            parser->error = 1;
            return count;
        }
        sel_one(parser, &buffer[count]);
        if (parser->error) {
            return count;
        }
        count++;
    }
    if (count == 0) {
        parser->error = 1;
    }
    return count;
}

/* Parse one complex selector (compounds joined by combinators) into *complex,
   allocating its compounds. Returns 0, or -1 with parser->error set. */
static int sel_complex_parse(sel_parser *parser, sel_complex *complex) {
    sel_compound temp[32];
    int count = 0;
    char combinator = ' ';
    while (1) {
        if (count >= 32) {
            parser->error = 1;
            break;
        }
        sel_simple simples[32];
        int simple_count = sel_compound_parse(parser, simples, 32);
        if (parser->error) {
            break;
        }
        sel_simple *owned = PyMem_Malloc((size_t)simple_count * sizeof(sel_simple));
        if (owned == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            parser->error = 1; /* GCOVR_EXCL_LINE: allocation-failure path */
            break;             /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        memcpy(owned, simples, (size_t)simple_count * sizeof(sel_simple));
        temp[count].simples = owned;
        temp[count].count = simple_count;
        temp[count].combinator = combinator;
        count++;
        int saw_ws = parser->pos < parser->len && is_space(parser->src[parser->pos]);
        sel_skip_ws(parser);
        if (parser->pos >= parser->len) {
            break;
        }
        Py_UCS4 ch = parser->src[parser->pos];
        if (ch == ',') {
            break;
        }
        if (ch == '>' || ch == '+' || ch == '~') {
            combinator = (char)ch;
            parser->pos++;
            sel_skip_ws(parser);
        } else if (saw_ws && sel_starts_simple(ch)) {
            combinator = ' ';
        } else {
            parser->error = 1;
            break;
        }
    }
    if (parser->error) {
        for (int index = 0; index < count; index++) {
            PyMem_Free(temp[index].simples);
        }
        return -1;
    }
    sel_compound *owned = PyMem_Malloc((size_t)count * sizeof(sel_compound));
    if (owned == NULL) {                  /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        for (int index = 0; index < count; index++) { /* GCOVR_EXCL_LINE: allocation-failure path */
            PyMem_Free(temp[index].simples);          /* GCOVR_EXCL_LINE: allocation-failure path */
        }                  /* GCOVR_EXCL_LINE: allocation-failure path */
        parser->error = 1; /* GCOVR_EXCL_LINE: allocation-failure path */
        return -1;         /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    memcpy(owned, temp, (size_t)count * sizeof(sel_compound));
    complex->compounds = owned;
    complex->count = count;
    return 0;
}

static void selector_free(sel_compiled *compiled) {
    for (int index = 0; index < compiled->count; index++) {
        for (int inner = 0; inner < compiled->alts[index].count; inner++) {
            PyMem_Free(compiled->alts[index].compounds[inner].simples);
        }
        PyMem_Free(compiled->alts[index].compounds);
    }
    PyMem_Free(compiled->alts);
    PyMem_Free(compiled->source);
    PyMem_Free(compiled);
}

/* Compile a selector string against the tree it will run on. Returns NULL with a
   ValueError set on a syntax error. */
static sel_compiled *selector_compile(th_tree *tree, PyObject *selector_str) {
    sel_compiled *compiled = PyMem_Calloc(1, sizeof(sel_compiled));
    if (compiled == NULL) {      /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return (void *)PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    compiled->source = PyUnicode_AsUCS4Copy(selector_str);
    if (compiled->source == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        PyMem_Free(compiled);       /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;                /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    sel_parser parser = {compiled->source, 0, PyUnicode_GET_LENGTH(selector_str), tree, 0};
    sel_complex temp[64];
    int count = 0;
    while (1) {
        sel_skip_ws(&parser);
        if (count >= 64) {
            parser.error = 1;
            break;
        }
        if (sel_complex_parse(&parser, &temp[count]) < 0) {
            break;
        }
        count++;
        sel_skip_ws(&parser);
        if (parser.pos >= parser.len) {
            break;
        }
        parser.pos++; /* a successful complex stops only at the end or a comma */
    }
    if (parser.error) { /* an empty or malformed selector always sets the error */
        for (int index = 0; index < count; index++) {
            for (int inner = 0; inner < temp[index].count; inner++) {
                PyMem_Free(temp[index].compounds[inner].simples);
            }
            PyMem_Free(temp[index].compounds);
        }
        PyMem_Free(compiled->source);
        PyMem_Free(compiled);
        PyErr_SetString(PyExc_ValueError, "invalid CSS selector");
        return NULL;
    }
    compiled->alts = PyMem_Malloc((size_t)count * sizeof(sel_complex));
    if (compiled->alts == NULL) {                     /* GCOVR_EXCL_BR_LINE: allocation cannot be forced */
        for (int index = 0; index < count; index++) { /* GCOVR_EXCL_LINE: allocation-failure path */
            for (int inner = 0; inner < temp[index].count; inner++) {    /* GCOVR_EXCL_LINE */
                PyMem_Free(temp[index].compounds[inner].simples);        /* GCOVR_EXCL_LINE */
            }                                  /* GCOVR_EXCL_LINE: allocation-failure path */
            PyMem_Free(temp[index].compounds); /* GCOVR_EXCL_LINE: allocation-failure path */
        }                                 /* GCOVR_EXCL_LINE: allocation-failure path */
        PyMem_Free(compiled->source); /* GCOVR_EXCL_LINE: allocation-failure path */
        PyMem_Free(compiled);         /* GCOVR_EXCL_LINE: allocation-failure path */
        return (void *)PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    memcpy(compiled->alts, temp, (size_t)count * sizeof(sel_complex));
    compiled->count = count;
    return compiled;
}

/* --------------------------------------------------------------- matching */

static Py_UCS4 sel_fold(Py_UCS4 ch, int ci) {
    return (ci && ch >= 'A' && ch <= 'Z') ? ch + 32 : ch;
}

static int sel_eq(const Py_UCS4 *a, Py_ssize_t alen, const Py_UCS4 *b, Py_ssize_t blen, int ci) {
    if (alen != blen) {
        return 0;
    }
    for (Py_ssize_t index = 0; index < alen; index++) {
        if (sel_fold(a[index], ci) != sel_fold(b[index], ci)) {
            return 0;
        }
    }
    return 1;
}

static const th_node_attr *sel_find_attr(th_node *node, uint32_t atom) {
    for (Py_ssize_t index = 0; index < node->attr_count; index++) {
        if (node->attrs[index].name_atom == atom) {
            return &node->attrs[index];
        }
    }
    return NULL;
}

/* Whether the attribute value satisfies the simple's operator and value. */
static int sel_match_attr_op(const sel_simple *simple, const Py_UCS4 *value, Py_ssize_t value_len) {
    const Py_UCS4 *want = simple->value;
    Py_ssize_t want_len = simple->value_len;
    switch (simple->op) {
    case OP_EXISTS:
        return 1;
    case OP_EQ:
        return sel_eq(value, value_len, want, want_len, simple->ci);
    case OP_PREFIX:
        return want_len > 0 && value_len >= want_len && sel_eq(value, want_len, want, want_len, simple->ci);
    case OP_SUFFIX:
        return want_len > 0 && value_len >= want_len &&
               sel_eq(value + (value_len - want_len), want_len, want, want_len, simple->ci);
    case OP_DASH:
        return sel_eq(value, value_len, want, want_len, simple->ci) ||
               (value_len > want_len && value[want_len] == '-' && sel_eq(value, want_len, want, want_len, simple->ci));
    case OP_INCLUDE: {
        if (want_len == 0) {
            return 0;
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
            if (cursor > start && sel_eq(value + start, cursor - start, want, want_len, simple->ci)) {
                return 1;
            }
        }
        return 0;
    }
    default: /* OP_SUBSTR */
        if (want_len == 0) {
            return 0;
        }
        for (Py_ssize_t start = 0; start + want_len <= value_len; start++) {
            if (sel_eq(value + start, want_len, want, want_len, simple->ci)) {
                return 1;
            }
        }
        return 0;
    }
}

static int sel_match_simple(th_node *node, const sel_simple *simple) {
    switch (simple->kind) {
    case '*':
        return 1;
    case 'e':
        if (simple->tag_atom != TH_TAG_UNKNOWN) {
            return node->atom == simple->tag_atom;
        }
        return sel_eq(node->text, node->text_len, simple->name, simple->name_len, 0);
    case '#': {
        const th_node_attr *attr = sel_find_attr(node, TH_ATTR_ID);
        return attr != NULL && attr->value != NULL && sel_eq(attr->value, attr->value_len, simple->name, simple->name_len, 0);
    }
    case '.': {
        const th_node_attr *attr = sel_find_attr(node, TH_ATTR_CLASS);
        if (attr == NULL || attr->value == NULL) {
            return 0;
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
            if (cursor > start && sel_eq(attr->value + start, cursor - start, simple->name, simple->name_len, 0)) {
                return 1;
            }
        }
        return 0;
    }
    default: { /* '[' */
        if (simple->attr_atom == UINT32_MAX) {
            return 0; /* no element in the tree carries this name */
        }
        const th_node_attr *attr = sel_find_attr(node, simple->attr_atom);
        if (attr == NULL) {
            return 0;
        }
        const Py_UCS4 *value = attr->value != NULL ? attr->value : simple->value;
        Py_ssize_t value_len = attr->value != NULL ? attr->value_len : 0;
        return sel_match_attr_op(simple, value, value_len);
    }
    }
}

static int sel_match_compound(th_node *node, const sel_compound *compound) {
    if (node->type != TH_NODE_ELEMENT) {
        return 0;
    }
    for (int index = 0; index < compound->count; index++) {
        if (!sel_match_simple(node, &compound->simples[index])) {
            return 0;
        }
    }
    return 1;
}

static th_node *sel_prev_element(th_node *node) {
    for (th_node *sibling = node->prev_sibling; sibling != NULL; sibling = sibling->prev_sibling) {
        if (sibling->type == TH_NODE_ELEMENT) {
            return sibling;
        }
    }
    return NULL;
}

/* node matches compounds[index]; verify the combinators and compounds to its
   left, with backtracking on the descendant and general-sibling axes. */
static int sel_match_from(th_node *node, const sel_complex *complex, int index) {
    if (index == 0) {
        return 1;
    }
    const sel_compound *target = &complex->compounds[index - 1];
    switch (complex->compounds[index].combinator) {
    case '>': {
        /* a matched node is an element, so it always has a parent (the document
           at the root), which sel_match_compound rejects as a non-element */
        th_node *parent = node->parent;
        return sel_match_compound(parent, target) && sel_match_from(parent, complex, index - 1);
    }
    case '+': {
        th_node *prev = sel_prev_element(node);
        return prev != NULL && sel_match_compound(prev, target) && sel_match_from(prev, complex, index - 1);
    }
    case '~':
        for (th_node *prev = sel_prev_element(node); prev != NULL; prev = sel_prev_element(prev)) {
            if (sel_match_compound(prev, target) && sel_match_from(prev, complex, index - 1)) {
                return 1;
            }
        }
        return 0;
    default: /* descendant */
        for (th_node *ancestor = node->parent; ancestor != NULL; ancestor = ancestor->parent) {
            if (sel_match_compound(ancestor, target) && sel_match_from(ancestor, complex, index - 1)) {
                return 1;
            }
        }
        return 0;
    }
}

static int selector_matches(th_node *node, const sel_compiled *compiled) {
    for (int index = 0; index < compiled->count; index++) {
        const sel_complex *complex = &compiled->alts[index];
        int subject = complex->count - 1;
        if (sel_match_compound(node, &complex->compounds[subject]) && sel_match_from(node, complex, subject)) {
            return 1;
        }
    }
    return 0;
}

#endif /* TURBOHTML_SELECTOR_H */
