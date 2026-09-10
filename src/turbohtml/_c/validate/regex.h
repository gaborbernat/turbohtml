/* A compact regular-expression matcher for the XSD `pattern` facet (and the RELAX NG
   equivalent). The pattern language is the XSD 1.0 regex subset: literals, `.`, escape
   classes (\d \D \w \W \s \S), character classes with ranges and negation, grouping,
   alternation, and the `? * + {m} {m,} {m,n}` quantifiers. It compiles to a Thompson
   NFA (Cox, "Regular Expression Matching Can Be Simple And Fast") and simulates it, so
   matching is linear in the input with no backtracking blow-up. Matching is anchored:
   the whole value must be consumed, as a facet requires. The parser is total -- an
   unrecognized metacharacter is taken as a literal -- so a schema never fails to
   compile over its pattern. Included once into datatypes.h; every definition is static. */

#ifndef TURBOHTML_VALIDATE_REGEX_H
#define TURBOHTML_VALIDATE_REGEX_H

enum {
    RX_BD = 1,  /* \d */
    RX_BW = 2,  /* \w */
    RX_BS = 4,  /* \s */
    RX_ND = 8,  /* \D */
    RX_NW = 16, /* \W */
    RX_NS = 32, /* \S */
};

typedef struct {
    Py_UCS4 lo, hi;
} rrange;

typedef struct {
    rrange *ranges;
    Py_ssize_t range_count, range_cap;
    int builtins;
    int negate;
} rclass;

enum { RN_EMPTY, RN_CHAR, RN_ANY, RN_CLASS, RN_CONCAT, RN_ALT, RN_QUEST, RN_STAR, RN_PLUS, RN_REPEAT };

typedef struct rnode {
    int type;
    Py_UCS4 ch;
    rclass *cls;
    struct rnode *a, *b;
    int rmin, rmax;
} rnode;

enum { RS_SPLIT, RS_MATCH, RS_ACCEPT };

typedef struct rstate {
    int kind;
    int mkind; /* RN_CHAR / RN_ANY / RN_CLASS */
    Py_UCS4 ch;
    rclass *cls;
    struct rstate *out, *out1;
    size_t index;
} rstate;

typedef struct {
    const Py_UCS4 *pattern;
    Py_ssize_t len, pos;
    arena *mem;
    int failed;
} rparser;

static rnode *rx_node(rparser *parser, int type) {
    rnode *node = arena_alloc(parser->mem, sizeof(rnode));
    if (node == NULL) {     /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        parser->failed = 1; /* GCOVR_EXCL_LINE */
        return NULL;        /* GCOVR_EXCL_LINE */
    }
    memset(node, 0, sizeof(*node));
    node->type = type;
    node->rmax = -1;
    return node;
}

static rnode *rx_parse_alt(rparser *parser);

static int rx_range_push(rparser *parser, rclass *cls, Py_UCS4 lo, Py_UCS4 hi) {
    if (cls->range_count == cls->range_cap) {
        size_t cap, bytes;
        const int fits =
            th_grow_cap((size_t)cls->range_count + 1, (size_t)cls->range_cap, 8, sizeof(rrange), &cap, &bytes);
        if (!fits) {            /* GCOVR_EXCL_BR_LINE: allocation size overflow */
            parser->failed = 1; /* GCOVR_EXCL_LINE: allocation size overflow */
            return -1;          /* GCOVR_EXCL_LINE: allocation size overflow */
        }
        rrange *grown = arena_alloc(parser->mem, bytes);
        if (grown == NULL) {    /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
            parser->failed = 1; /* GCOVR_EXCL_LINE */
            return -1;          /* GCOVR_EXCL_LINE */
        }
        if (cls->range_count > 0) {
            memcpy(grown, cls->ranges, (size_t)cls->range_count * sizeof(rrange));
        }
        cls->ranges = grown;
        cls->range_cap = (Py_ssize_t)cap;
    }
    cls->ranges[cls->range_count].lo = lo;
    cls->ranges[cls->range_count].hi = hi;
    cls->range_count++;
    return 0;
}

/* Map a class escape letter to its builtin flag, or 0 when it is not one. */
static int rx_builtin_flag(Py_UCS4 letter) {
    switch (letter) {
    case 'd':
        return RX_BD;
    case 'w':
        return RX_BW;
    case 's':
        return RX_BS;
    case 'D':
        return RX_ND;
    case 'W':
        return RX_NW;
    case 'S':
        return RX_NS;
    default:
        return 0;
    }
}

/* The literal a backslash escape stands for (\n \t \r or the escaped metacharacter). */
static Py_UCS4 rx_escape_literal(Py_UCS4 letter) {
    switch (letter) {
    case 'n':
        return '\n';
    case 't':
        return '\t';
    case 'r':
        return '\r';
    default:
        return letter;
    }
}

static rnode *rx_parse_class(rparser *parser) {
    rnode *node = rx_node(parser, RN_CLASS);
    if (node == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        return NULL;    /* GCOVR_EXCL_LINE */
    }
    rclass *cls = arena_alloc(parser->mem, sizeof(rclass));
    if (cls == NULL) {      /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        parser->failed = 1; /* GCOVR_EXCL_LINE */
        return NULL;        /* GCOVR_EXCL_LINE */
    }
    memset(cls, 0, sizeof(*cls));
    node->cls = cls;
    if (parser->pos < parser->len && parser->pattern[parser->pos] == '^') {
        cls->negate = 1;
        parser->pos++;
    }
    while (parser->pos < parser->len && parser->pattern[parser->pos] != ']') {
        Py_UCS4 current = parser->pattern[parser->pos++];
        if (current == '\\' && parser->pos < parser->len) {
            Py_UCS4 letter = parser->pattern[parser->pos++];
            int flag = rx_builtin_flag(letter);
            if (flag != 0) {
                cls->builtins |= flag;
                continue;
            }
            current = rx_escape_literal(letter);
        }
        if (parser->pos + 1 < parser->len && parser->pattern[parser->pos] == '-' &&
            parser->pattern[parser->pos + 1] != ']') {
            Py_UCS4 hi = parser->pattern[parser->pos + 1];
            parser->pos += 2;
            if (hi == '\\' && parser->pos < parser->len) {
                hi = rx_escape_literal(parser->pattern[parser->pos++]);
            }
            if (rx_range_push(parser, cls, current, hi) < 0) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
                return NULL;                                   /* GCOVR_EXCL_LINE */
            }
        } else if (rx_range_push(parser, cls, current, current) < 0) { /* GCOVR_EXCL_BR_LINE: arena OOM unforceable */
            return NULL;                                               /* GCOVR_EXCL_LINE */
        }
    }
    if (parser->pos < parser->len) { /* consume the closing ']' when present */
        parser->pos++;
    }
    return node;
}

static rnode *rx_class_from_builtin(rparser *parser, int flag) {
    rnode *node = rx_node(parser, RN_CLASS);
    if (node == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        return NULL;    /* GCOVR_EXCL_LINE */
    }
    rclass *cls = arena_alloc(parser->mem, sizeof(rclass));
    if (cls == NULL) {      /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        parser->failed = 1; /* GCOVR_EXCL_LINE */
        return NULL;        /* GCOVR_EXCL_LINE */
    }
    memset(cls, 0, sizeof(*cls));
    cls->builtins = flag;
    node->cls = cls;
    return node;
}

static rnode *rx_parse_atom(rparser *parser) {
    Py_UCS4 current = parser->pattern[parser->pos];
    if (current == '(') {
        parser->pos++;
        rnode *inner = rx_parse_alt(parser);
        /* rx_parse_alt stops at ')' or end of input, so a remaining char here is the ')' */
        if (parser->pos < parser->len) {
            parser->pos++;
        }
        return inner;
    }
    if (current == '[') {
        parser->pos++;
        return rx_parse_class(parser);
    }
    if (current == '.') {
        parser->pos++;
        return rx_node(parser, RN_ANY);
    }
    if (current == '\\' && parser->pos + 1 < parser->len) {
        Py_UCS4 letter = parser->pattern[parser->pos + 1];
        int flag = rx_builtin_flag(letter);
        parser->pos += 2;
        if (flag != 0) {
            return rx_class_from_builtin(parser, flag);
        }
        rnode *node = rx_node(parser, RN_CHAR);
        if (node != NULL) { /* GCOVR_EXCL_BR_LINE: node is NULL only on unforceable arena OOM */
            node->ch = rx_escape_literal(letter);
        }
        return node;
    }
    parser->pos++;
    rnode *node = rx_node(parser, RN_CHAR);
    if (node != NULL) { /* GCOVR_EXCL_BR_LINE: node is NULL only on unforceable arena OOM */
        node->ch = current;
    }
    return node;
}

/* Parse a {m}, {m,} or {m,n} quantifier starting at the '{'. Returns 1 with rmin and
   rmax set (rmax -1 for unbounded), or 0 leaving pos unchanged when not a quantifier. */
static int rx_parse_bound(rparser *parser, int *rmin, int *rmax) {
    Py_ssize_t save = parser->pos;
    parser->pos++; /* past '{' */
    Py_ssize_t low = 0, digits = 0;
    while (parser->pos < parser->len && parser->pattern[parser->pos] >= '0' && parser->pattern[parser->pos] <= '9') {
        low = low * 10 + (parser->pattern[parser->pos++] - '0');
        digits++;
    }
    if (digits == 0) {
        parser->pos = save;
        return 0;
    }
    int high = (int)low;
    if (parser->pos < parser->len && parser->pattern[parser->pos] == ',') {
        parser->pos++;
        Py_ssize_t hi = 0, hi_digits = 0;
        while (parser->pos < parser->len && parser->pattern[parser->pos] >= '0' &&
               parser->pattern[parser->pos] <= '9') {
            hi = hi * 10 + (parser->pattern[parser->pos++] - '0');
            hi_digits++;
        }
        high = hi_digits == 0 ? -1 : (int)hi;
    }
    if (parser->pos >= parser->len || parser->pattern[parser->pos] != '}') {
        parser->pos = save;
        return 0;
    }
    parser->pos++;
    *rmin = (int)low;
    *rmax = high;
    return 1;
}

static rnode *rx_parse_quant(rparser *parser) {
    rnode *atom = rx_parse_atom(parser);
    if (atom == NULL || parser->pos >= parser->len) { /* GCOVR_EXCL_BR_LINE: NULL only on unforceable arena OOM */
        return atom;
    }
    Py_UCS4 quant = parser->pattern[parser->pos];
    int type = quant == '?' ? RN_QUEST : (quant == '*' ? RN_STAR : (quant == '+' ? RN_PLUS : -1));
    if (type != -1) {
        parser->pos++;
        rnode *node = rx_node(parser, type);
        if (node != NULL) { /* GCOVR_EXCL_BR_LINE: node is NULL only on unforceable arena OOM */
            node->a = atom;
        }
        return node;
    }
    if (quant == '{') {
        int rmin, rmax;
        if (rx_parse_bound(parser, &rmin, &rmax)) {
            rnode *node = rx_node(parser, RN_REPEAT);
            if (node != NULL) { /* GCOVR_EXCL_BR_LINE: node is NULL only on unforceable arena OOM */
                node->a = atom;
                node->rmin = rmin;
                node->rmax = rmax;
            }
            return node;
        }
    }
    return atom;
}

static rnode *rx_parse_concat(rparser *parser) {
    rnode *left = NULL;
    while (parser->pos < parser->len && parser->pattern[parser->pos] != '|' && parser->pattern[parser->pos] != ')') {
        rnode *piece = rx_parse_quant(parser);
        if (piece == NULL) { /* GCOVR_EXCL_BR_LINE: NULL only on unforceable arena OOM */
            return NULL;     /* GCOVR_EXCL_LINE */
        }
        if (left == NULL) {
            left = piece;
        } else {
            rnode *cat = rx_node(parser, RN_CONCAT);
            if (cat == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
                return NULL;   /* GCOVR_EXCL_LINE */
            }
            cat->a = left;
            cat->b = piece;
            left = cat;
        }
    }
    return left == NULL ? rx_node(parser, RN_EMPTY) : left;
}

static rnode *rx_parse_alt(rparser *parser) {
    rnode *left = rx_parse_concat(parser);
    while (parser->pos < parser->len && parser->pattern[parser->pos] == '|') {
        parser->pos++;
        rnode *right = rx_parse_concat(parser);
        rnode *alt = rx_node(parser, RN_ALT);
        if (left == NULL || right == NULL || alt == NULL) { /* GCOVR_EXCL_BR_LINE: NULL only on unforceable arena OOM */
            return NULL;                                    /* GCOVR_EXCL_LINE */
        }
        alt->a = left;
        alt->b = right;
        left = alt;
    }
    return left;
}

typedef struct {
    arena *mem;
    size_t count;
    int failed;
} rcompiler;

static rstate *rx_state(rcompiler *compiler, int kind) {
    rstate *state = arena_alloc(compiler->mem, sizeof(rstate));
    if (state == NULL) {      /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        compiler->failed = 1; /* GCOVR_EXCL_LINE */
        return NULL;          /* GCOVR_EXCL_LINE */
    }
    memset(state, 0, sizeof(*state));
    state->kind = kind;
    state->index = compiler->count++;
    return state;
}

static rstate *rx_compile(rcompiler *compiler, rnode *node, rstate *out);

static rstate *rx_compile_repeat(rcompiler *compiler, rnode *node, int rmin, int rmax, rstate *out) {
    if (rmin > 0) {
        rstate *tail = rx_compile_repeat(compiler, node, rmin - 1, rmax < 0 ? -1 : rmax - 1, out);
        return tail == NULL ? NULL : rx_compile(compiler, node->a, tail); /* GCOVR_EXCL_BR_LINE: NULL only on OOM */
    }
    if (rmax < 0) {
        rstate *split = rx_state(compiler, RS_SPLIT);
        if (split == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
            return NULL;     /* GCOVR_EXCL_LINE */
        }
        split->out1 = out;
        split->out = rx_compile(compiler, node->a, split);
        return split;
    }
    if (rmax == 0) {
        return out;
    }
    rstate *split = rx_state(compiler, RS_SPLIT);
    if (split == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        return NULL;     /* GCOVR_EXCL_LINE */
    }
    rstate *tail = rx_compile_repeat(compiler, node, 0, rmax - 1, out);
    split->out1 = out;
    split->out = tail == NULL ? NULL : rx_compile(compiler, node->a, tail); /* GCOVR_EXCL_BR_LINE: NULL only on OOM */
    return split;
}

/* Compile an AST node into an NFA fragment whose every exit flows to `out`. */
static rstate *rx_compile(rcompiler *compiler, rnode *node, rstate *out) {
    if (node == NULL) { /* GCOVR_EXCL_BR_LINE: NULL only on unforceable arena OOM */
        return NULL;    /* GCOVR_EXCL_LINE */
    }
    switch (node->type) {
    case RN_EMPTY:
        return out;
    case RN_CHAR:
    case RN_ANY:
    case RN_CLASS: {
        rstate *state = rx_state(compiler, RS_MATCH);
        if (state == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
            return NULL;     /* GCOVR_EXCL_LINE */
        }
        state->mkind = node->type;
        state->ch = node->ch;
        state->cls = node->cls;
        state->out = out;
        return state;
    }
    case RN_CONCAT: {
        rstate *tail = rx_compile(compiler, node->b, out);
        return tail == NULL ? NULL : rx_compile(compiler, node->a, tail); /* GCOVR_EXCL_BR_LINE: NULL only on OOM */
    }
    case RN_ALT: {
        rstate *split = rx_state(compiler, RS_SPLIT);
        if (split == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
            return NULL;     /* GCOVR_EXCL_LINE */
        }
        split->out = rx_compile(compiler, node->a, out);
        split->out1 = rx_compile(compiler, node->b, out);
        return split;
    }
    case RN_QUEST: {
        rstate *split = rx_state(compiler, RS_SPLIT);
        if (split == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
            return NULL;     /* GCOVR_EXCL_LINE */
        }
        split->out = rx_compile(compiler, node->a, out);
        split->out1 = out;
        return split;
    }
    case RN_STAR: {
        rstate *split = rx_state(compiler, RS_SPLIT);
        if (split == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
            return NULL;     /* GCOVR_EXCL_LINE */
        }
        split->out1 = out;
        split->out = rx_compile(compiler, node->a, split);
        return split;
    }
    case RN_PLUS: {
        rstate *split = rx_state(compiler, RS_SPLIT);
        if (split == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
            return NULL;     /* GCOVR_EXCL_LINE */
        }
        split->out1 = out;
        rstate *start = rx_compile(compiler, node->a, split);
        split->out = start;
        return start;
    }
    default:
        return rx_compile_repeat(compiler, node, node->rmin, node->rmax, out);
    }
}

static int rx_class_match(const rclass *cls, Py_UCS4 codepoint) {
    int inside = 0;
    for (Py_ssize_t index = 0; index < cls->range_count; index++) {
        if (codepoint >= cls->ranges[index].lo && codepoint <= cls->ranges[index].hi) {
            inside = 1;
        }
    }
    int is_d = is_digit(codepoint);
    int is_w = is_name_char(codepoint) && codepoint != '-' && codepoint != '.';
    int is_s = is_xml_space(codepoint);
    if ((cls->builtins & RX_BD) && is_d) {
        inside = 1;
    }
    if ((cls->builtins & RX_BW) && is_w) {
        inside = 1;
    }
    if ((cls->builtins & RX_BS) && is_s) {
        inside = 1;
    }
    if ((cls->builtins & RX_ND) && !is_d) {
        inside = 1;
    }
    if ((cls->builtins & RX_NW) && !is_w) {
        inside = 1;
    }
    if ((cls->builtins & RX_NS) && !is_s) {
        inside = 1;
    }
    return cls->negate ? !inside : inside;
}

static int rx_state_match(const rstate *state, Py_UCS4 codepoint) {
    if (state->mkind == RN_CHAR) {
        return state->ch == codepoint;
    }
    if (state->mkind == RN_ANY) {
        return codepoint != '\n' && codepoint != '\r';
    }
    return rx_class_match(state->cls, codepoint);
}

typedef struct rpattern {
    const Py_UCS4 *text;
    Py_ssize_t len;
    rstate *start;
    size_t count;
    struct rpattern *next;
} rpattern;

static int regex_cache_add(th_schema *schema, const Py_UCS4 *text, Py_ssize_t len) {
    for (rpattern *cached = schema->regex_patterns; cached != NULL; cached = cached->next) {
        if (u_eq_u(text, len, cached->text, cached->len)) {
            return 0;
        }
    }
    rpattern *pattern = arena_alloc(&schema->mem, sizeof(*pattern));
    if (pattern == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        return -1;         /* GCOVR_EXCL_LINE */
    }
    rparser parser = {text, len, 0, &schema->mem, 0};
    rnode *ast = rx_parse_alt(&parser);
    rcompiler compiler = {&schema->mem, 0, 0};
    rstate *accept = rx_state(&compiler, RS_ACCEPT);
    if (parser.failed || ast == NULL || accept == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        return -1;                                        /* GCOVR_EXCL_LINE */
    }
    rstate *start = rx_compile(&compiler, ast, accept);
    if (start == NULL || compiler.failed) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        return -1;                          /* GCOVR_EXCL_LINE */
    }
    pattern->text = text;
    pattern->len = len;
    pattern->start = start;
    pattern->count = compiler.count;
    pattern->next = schema->regex_patterns;
    schema->regex_patterns = pattern;
    return 0;
}

static int regex_cache_schema(th_schema *schema, th_node *node) {
    if (schema->kind == 0 && is_schema_el(schema, node, XSD_NS, "pattern")) {
        const th_node_attr *value = attr_exact(schema->tree, node, "value", 5);
        if (value != NULL) {
            if (regex_cache_add(schema, value->value, value->value_len) < 0) { /* GCOVR_EXCL_BR_LINE: arena OOM */
                return -1;                                                     /* GCOVR_EXCL_LINE */
            }
        }
    } else if (schema->kind != 0 && is_schema_el(schema, node, RNG_NS, "param")) {
        const th_node_attr *name = attr_exact(schema->tree, node, "name", 4);
        if (name != NULL && u_eq_ascii(name->value, name->value_len, "pattern")) {
            Py_ssize_t len = 0;
            const Py_UCS4 *text = element_text_raw(schema->tree, node, &len);
            if (regex_cache_add(schema, text, len) < 0) { /* GCOVR_EXCL_BR_LINE: arena OOM */
                return -1;                                /* GCOVR_EXCL_LINE */
            }
        }
    }
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        if (child->type == TH_NODE_ELEMENT) {
            if (regex_cache_schema(schema, child) < 0) { /* GCOVR_EXCL_BR_LINE: arena OOM */
                return -1;                               /* GCOVR_EXCL_LINE */
            }
        }
    }
    return 0;
}

typedef struct {
    const rstate **items;
    size_t len;
} rlist;

static void rx_add(rlist *list, const rstate *state, size_t *visited, size_t gen) {
    if (visited[state->index] == gen) {
        return;
    }
    visited[state->index] = gen;
    if (state->kind == RS_SPLIT) {
        rx_add(list, state->out, visited, gen);
        rx_add(list, state->out1, visited, gen);
        return;
    }
    list->items[list->len++] = state;
}

static int regex_full_match(th_schema *schema, const Py_UCS4 *text, Py_ssize_t text_len, const Py_UCS4 *value,
                            Py_ssize_t len) {
    const rpattern *pattern = schema->regex_patterns;
    while (!u_eq_u(text, text_len, pattern->text, pattern->len)) {
        pattern = pattern->next;
    }
    const rstate **storage = arena_alloc(&schema->mem, pattern->count * 2 * sizeof(rstate *));
    size_t *visited = arena_alloc(&schema->mem, pattern->count * sizeof(size_t));
    if (storage == NULL || visited == NULL) { /* GCOVR_EXCL_BR_LINE: arena OOM is unforceable */
        return 1;                             /* GCOVR_EXCL_LINE */
    }
    memset(visited, 0, pattern->count * sizeof(size_t));
    rlist current = {storage, 0};
    rlist next = {storage + pattern->count, 0};
    size_t gen = 1;
    rx_add(&current, pattern->start, visited, gen);
    for (Py_ssize_t index = 0; index < len; index++) {
        gen++;
        next.len = 0;
        for (size_t state = 0; state < current.len; state++) {
            if (current.items[state]->kind == RS_MATCH && rx_state_match(current.items[state], value[index])) {
                rx_add(&next, current.items[state]->out, visited, gen);
            }
        }
        rlist swap = current;
        current = next;
        next = swap;
    }
    for (size_t state = 0; state < current.len; state++) {
        if (current.items[state]->kind == RS_ACCEPT) {
            return 1;
        }
    }
    return 0;
}

#endif /* TURBOHTML_VALIDATE_REGEX_H */
