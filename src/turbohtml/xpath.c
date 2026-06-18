/* XPath 1.0 front end: lexer + recursive-descent parser building a flat arena AST.

   The grammar is the XPath 1.0 one (W3C REC-xpath-19991116), parsed by a precedence
   ladder of recursive-descent productions (Or > And > Equality > Relational >
   Additive > Multiplicative > Unary > Union > Path > Filter > Step > Primary). The
   abbreviations are expanded as they are parsed: `//` becomes a descendant-or-self
   node() step, `@x` an attribute step, `.` a self node() step, `..` a parent node()
   step. The result is an array of fixed-size tagged nodes referenced by int32 index
   (not pointers), so the program is one contiguous block, cheap to share and free.

   The lexer carries XPath's context-sensitive disambiguation: an NCName that spells
   and/or/div/mod is an operator only when an operator could appear (the preceding
   token is not one of @ :: ( [ , or an operator), and `*` is a wildcard in a node
   test but a multiply operator after a node test or value. */

#include "turbohtml.h"
#include "xpath.h"

#include <math.h>
#include <string.h>

/* ----------------------------------------------------------------- AST */

enum xn_kind {
    XN_OR,
    XN_AND,
    XN_EQ,
    XN_NE,
    XN_LT,
    XN_LE,
    XN_GT,
    XN_GE,
    XN_ADD,
    XN_SUB,
    XN_MUL,
    XN_DIV,
    XN_MOD,
    XN_NEG,    /* unary minus: a = operand */
    XN_UNION,  /* a | b */
    XN_NUM,    /* num literal */
    XN_LIT,    /* string literal: str/str_len */
    XN_PATH,   /* absolute flag; a = first step; b = filter primary or -1 */
    XN_STEP,   /* axis/test/name; a = first predicate (XN_PRED chain); next = next step */
    XN_PRED,   /* predicate wrapper: a = expr; next = next predicate */
    XN_FUNC,   /* function call: str=name; a = first arg (chained by next) */
    XN_FILTER, /* FilterExpr: a = primary; b = predicate chain (applied to the whole set) */
};

enum xp_axis {
    AX_CHILD,
    AX_DESCENDANT,
    AX_DESCENDANT_OR_SELF,
    AX_ATTRIBUTE,
    AX_SELF,
    AX_PARENT,
    AX_ANCESTOR,
    AX_ANCESTOR_OR_SELF,
    AX_FOLLOWING_SIBLING,
    AX_PRECEDING_SIBLING,
    AX_FOLLOWING,
    AX_PRECEDING,
    AX_NAMESPACE,
};

enum xp_test {
    NT_NAME,    /* a QName/NCName name test; str holds the (copied) name */
    NT_STAR,    /* * */
    NT_NODE,    /* node() */
    NT_TEXT,    /* text() */
    NT_COMMENT, /* comment() */
    NT_PI,      /* processing-instruction(); str holds the optional literal target */
};

typedef struct {
    uint8_t kind;     /* enum xn_kind */
    uint8_t axis;     /* enum xp_axis (XN_STEP) */
    uint8_t test;     /* enum xp_test (XN_STEP) */
    uint8_t absolute; /* XN_PATH: a leading / was present */
    int32_t a;        /* first child / operand */
    int32_t b;        /* second child */
    int32_t next;     /* sibling chain: steps, predicates, args */
    double num;       /* XN_NUM */
    Py_UCS4 *str;     /* owned name/literal; NULL when none */
    Py_ssize_t str_len;
} xn;

struct xp_program {
    xn *nodes;
    int32_t count;
    int32_t cap;
    int32_t root; /* index of the root expression */
};

/* Append a blank node, returning its index or -1 on OOM. */
static int32_t xn_new(xp_program *p, enum xn_kind kind) {
    if (p->count == p->cap) {
        int32_t cap = p->cap ? p->cap * 2 : 16;
        xn *grown = PyMem_Realloc(p->nodes, (size_t)cap * sizeof(xn));
        if (grown == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return -1;       /* GCOVR_EXCL_LINE */
        }
        p->nodes = grown;
        p->cap = cap;
    }
    int32_t idx = p->count++;
    xn *n = &p->nodes[idx];
    memset(n, 0, sizeof(*n));
    n->kind = (uint8_t)kind;
    n->a = n->b = n->next = -1;
    return idx;
}

/* ----------------------------------------------------------------- lexer */

typedef enum {
    TK_EOF,
    TK_SLASH,
    TK_DSLASH,
    TK_LBRACK,
    TK_RBRACK,
    TK_LPAREN,
    TK_RPAREN,
    TK_AT,
    TK_COMMA,
    TK_DOT,
    TK_DOTDOT,
    TK_PIPE,
    TK_COLONCOLON,
    TK_PLUS,
    TK_MINUS,
    TK_STAR,
    TK_EQ,
    TK_NE,
    TK_LT,
    TK_LE,
    TK_GT,
    TK_GE,
    TK_NUM,
    TK_LITERAL,
    TK_NAME,
    TK_AND,
    TK_OR,
    TK_DIV,
    TK_MOD,
} tok_kind;

typedef struct {
    const Py_UCS4 *src;
    Py_ssize_t len;
    Py_ssize_t pos;
    tok_kind kind;
    const Py_UCS4 *tstart; /* NAME / LITERAL text (into src) */
    Py_ssize_t tlen;
    double num;     /* NUM value */
    int op_context; /* an operator may appear here (disambiguation state) */
    int error;      /* a lexical error was hit */
} lexer;

static int xp_is_name_start(Py_UCS4 c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_' || c >= 0x80;
}

static int xp_is_name_char(Py_UCS4 c) {
    return xp_is_name_start(c) || (c >= '0' && c <= '9') || c == '-' || c == '.';
}

static int xp_is_space(Py_UCS4 c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}

static int xp_name_eq(const lexer *lx, const char *kw) {
    Py_ssize_t i = 0;
    for (; kw[i] != '\0'; i++) {
        if (i >= lx->tlen || lx->tstart[i] != (Py_UCS4)(unsigned char)kw[i]) {
            return 0;
        }
    }
    return i == lx->tlen;
}

/* Whether the just-produced token means the next `*`/NCName sits in operator
   position (XPath's special tokenization rule). */
static int xp_op_follows(tok_kind kind) {
    switch (kind) {
    case TK_AT:
    case TK_COLONCOLON:
    case TK_LPAREN:
    case TK_LBRACK:
    case TK_COMMA:
    case TK_SLASH:
    case TK_DSLASH:
    case TK_PIPE:
    case TK_PLUS:
    case TK_MINUS:
    case TK_STAR:
    case TK_EQ:
    case TK_NE:
    case TK_LT:
    case TK_LE:
    case TK_GT:
    case TK_GE:
    case TK_AND:
    case TK_OR:
    case TK_DIV:
    case TK_MOD:
        return 0; /* after these, the next token is in value (non-operator) position */
    default:
        return 1; /* after a name/number/literal/) /] /. /.. the next is operator position */
    }
}

static void lex_next(lexer *lx) {
    while (lx->pos < lx->len && xp_is_space(lx->src[lx->pos])) {
        lx->pos++;
    }
    int prev_op = lx->op_context;
    if (lx->pos >= lx->len) {
        lx->kind = TK_EOF;
        return;
    }
    Py_UCS4 c = lx->src[lx->pos];
    Py_UCS4 d = lx->pos + 1 < lx->len ? lx->src[lx->pos + 1] : 0;
    switch (c) {
    case '/':
        lx->pos += d == '/' ? 2 : 1;
        lx->kind = d == '/' ? TK_DSLASH : TK_SLASH;
        break;
    case '[':
        lx->pos++;
        lx->kind = TK_LBRACK;
        break;
    case ']':
        lx->pos++;
        lx->kind = TK_RBRACK;
        break;
    case '(':
        lx->pos++;
        lx->kind = TK_LPAREN;
        break;
    case ')':
        lx->pos++;
        lx->kind = TK_RPAREN;
        break;
    case '@':
        lx->pos++;
        lx->kind = TK_AT;
        break;
    case ',':
        lx->pos++;
        lx->kind = TK_COMMA;
        break;
    case '|':
        lx->pos++;
        lx->kind = TK_PIPE;
        break;
    case '+':
        lx->pos++;
        lx->kind = TK_PLUS;
        break;
    case '-':
        lx->pos++;
        lx->kind = TK_MINUS;
        break;
    case '*':
        lx->pos++;
        lx->kind = TK_STAR;
        break;
    case '=':
        lx->pos++;
        lx->kind = TK_EQ;
        break;
    case '!':
        if (d == '=') {
            lx->pos += 2;
            lx->kind = TK_NE;
        } else {
            lx->error = 1;
            lx->kind = TK_EOF;
        }
        break;
    case '<':
        lx->pos += d == '=' ? 2 : 1;
        lx->kind = d == '=' ? TK_LE : TK_LT;
        break;
    case '>':
        lx->pos += d == '=' ? 2 : 1;
        lx->kind = d == '=' ? TK_GE : TK_GT;
        break;
    case ':':
        if (d == ':') {
            lx->pos += 2;
            lx->kind = TK_COLONCOLON;
        } else {
            lx->error = 1;
            lx->kind = TK_EOF;
        }
        break;
    case '"':
    case '\'': {
        Py_ssize_t start = ++lx->pos;
        while (lx->pos < lx->len && lx->src[lx->pos] != c) {
            lx->pos++;
        }
        if (lx->pos >= lx->len) {
            lx->error = 1;
            lx->kind = TK_EOF;
            break;
        }
        lx->tstart = lx->src + start;
        lx->tlen = lx->pos - start;
        lx->pos++; /* closing quote */
        lx->kind = TK_LITERAL;
        break;
    }
    case '.':
        if (d == '.') {
            lx->pos += 2;
            lx->kind = TK_DOTDOT;
        } else if (d >= '0' && d <= '9') {
            goto number;
        } else {
            lx->pos++;
            lx->kind = TK_DOT;
        }
        break;
    default:
        if (c >= '0' && c <= '9') {
            goto number;
        }
        if (xp_is_name_start(c)) {
            Py_ssize_t start = lx->pos;
            while (lx->pos < lx->len && xp_is_name_char(lx->src[lx->pos])) {
                lx->pos++;
            }
            lx->tstart = lx->src + start;
            lx->tlen = lx->pos - start;
            lx->kind = TK_NAME;
            if (prev_op) {
                if (xp_name_eq(lx, "and")) {
                    lx->kind = TK_AND;
                } else if (xp_name_eq(lx, "or")) {
                    lx->kind = TK_OR;
                } else if (xp_name_eq(lx, "div")) {
                    lx->kind = TK_DIV;
                } else if (xp_name_eq(lx, "mod")) {
                    lx->kind = TK_MOD;
                }
            }
        } else {
            lx->error = 1;
            lx->kind = TK_EOF;
        }
        break;
    number: {
        Py_ssize_t start = lx->pos;
        while (lx->pos < lx->len && lx->src[lx->pos] >= '0' && lx->src[lx->pos] <= '9') {
            lx->pos++;
        }
        if (lx->pos < lx->len && lx->src[lx->pos] == '.') {
            lx->pos++;
            while (lx->pos < lx->len && lx->src[lx->pos] >= '0' && lx->src[lx->pos] <= '9') {
                lx->pos++;
            }
        }
        double value = 0.0;
        double frac = 0.0;
        double scale = 1.0;
        int after_dot = 0;
        for (Py_ssize_t i = start; i < lx->pos; i++) {
            Py_UCS4 ch = lx->src[i];
            if (ch == '.') {
                after_dot = 1;
            } else if (!after_dot) {
                value = value * 10.0 + (ch - '0');
            } else {
                scale *= 10.0;
                frac += (ch - '0') / scale;
            }
        }
        lx->num = value + frac;
        lx->kind = TK_NUM;
        break;
    }
    }
    lx->op_context = xp_op_follows(lx->kind);
}

/* ---------------------------------------------------------------- parser */

typedef struct {
    lexer lx;
    xp_program *p;
    int failed;
    const char *msg;
} parser;

static void fail(parser *ps, const char *msg) {
    if (!ps->failed) {
        ps->failed = 1;
        ps->msg = msg;
    }
}

static int32_t parse_expr(parser *ps);
static int32_t parse_union(parser *ps);

static int accept(parser *ps, tok_kind kind) {
    /* a lexer error always leaves kind == TK_EOF, and accept is never called with
       TK_EOF, so kind == the (non-EOF) target already implies no pending error */
    if (ps->lx.kind == kind) {
        lex_next(&ps->lx);
        if (ps->lx.error) {
            fail(ps, "invalid character in expression");
        }
        return 1;
    }
    return 0;
}

static void expect(parser *ps, tok_kind kind, const char *msg) {
    if (!accept(ps, kind)) {
        fail(ps, msg);
    }
}

/* Copy the lexer's current NAME/LITERAL text into the node's owned string. */
static int copy_text(xp_program *p, int32_t idx, const Py_UCS4 *src, Py_ssize_t len) {
    Py_UCS4 *buf = PyMem_Malloc((size_t)(len ? len : 1) * sizeof(Py_UCS4));
    if (buf == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;     /* GCOVR_EXCL_LINE */
    }
    memcpy(buf, src, (size_t)len * sizeof(Py_UCS4));
    p->nodes[idx].str = buf;
    p->nodes[idx].str_len = len;
    return 0;
}

/* A NodeTest after an axis has been chosen; fills test/str on the step node. */
static void parse_node_test(parser *ps, int32_t step) {
    lexer *lx = &ps->lx;
    if (lx->kind == TK_STAR) {
        ps->p->nodes[step].test = NT_STAR;
        lex_next(lx);
        return;
    }
    if (lx->kind != TK_NAME) {
        fail(ps, "expected a node test");
        return;
    }
    /* node()/text()/comment()/processing-instruction() when followed by '(' */
    int is_node = xp_name_eq(lx, "node");
    int is_text = xp_name_eq(lx, "text");
    int is_comment = xp_name_eq(lx, "comment");
    int is_pi = xp_name_eq(lx, "processing-instruction");
    Py_ssize_t save = lx->pos;
    while (save < lx->len && xp_is_space(lx->src[save])) {
        save++;
    }
    int kind_test = (is_node || is_text || is_comment || is_pi) && save < lx->len && lx->src[save] == '(';
    if (kind_test) {
        ps->p->nodes[step].test = (uint8_t)(is_node ? NT_NODE : is_text ? NT_TEXT : is_comment ? NT_COMMENT : NT_PI);
        lex_next(lx); /* the name */
        expect(ps, TK_LPAREN, "expected '('");
        if (is_pi && lx->kind == TK_LITERAL) {
            if (copy_text(ps->p, step, lx->tstart, lx->tlen) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                fail(ps, "out of memory");                          /* GCOVR_EXCL_LINE */
            }
            lex_next(lx);
        }
        expect(ps, TK_RPAREN, "expected ')'");
        return;
    }
    ps->p->nodes[step].test = NT_NAME;
    if (copy_text(ps->p, step, lx->tstart, lx->tlen) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
        fail(ps, "out of memory");                          /* GCOVR_EXCL_LINE */
    }
    lex_next(lx);
}

/* Parse the predicate list onto a step (or filter), returning the head index. */
static int32_t parse_predicates(parser *ps) {
    int32_t head = -1;
    int32_t tail = -1;
    while (ps->lx.kind == TK_LBRACK) {
        lex_next(&ps->lx);
        int32_t pred = xn_new(ps->p, XN_PRED);
        if (pred < 0) {                /* GCOVR_EXCL_BR_LINE: alloc */
            fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
            return head;               /* GCOVR_EXCL_LINE */
        }
        int32_t expr = parse_expr(ps);
        ps->p->nodes[pred].a = expr;
        expect(ps, TK_RBRACK, "expected ']'");
        if (head < 0) {
            head = pred;
        } else {
            ps->p->nodes[tail].next = pred;
        }
        tail = pred;
    }
    return head;
}

static int axis_from_name(const lexer *lx, enum xp_axis *out) {
    static const struct {
        const char *name;
        enum xp_axis axis;
    } table[] = {
        {"child", AX_CHILD},
        {"descendant", AX_DESCENDANT},
        {"descendant-or-self", AX_DESCENDANT_OR_SELF},
        {"attribute", AX_ATTRIBUTE},
        {"self", AX_SELF},
        {"parent", AX_PARENT},
        {"ancestor", AX_ANCESTOR},
        {"ancestor-or-self", AX_ANCESTOR_OR_SELF},
        {"following-sibling", AX_FOLLOWING_SIBLING},
        {"preceding-sibling", AX_PRECEDING_SIBLING},
        {"following", AX_FOLLOWING},
        {"preceding", AX_PRECEDING},
        {"namespace", AX_NAMESPACE},
    };
    for (size_t i = 0; i < sizeof(table) / sizeof(table[0]); i++) {
        if (xp_name_eq(lx, table[i].name)) {
            *out = table[i].axis;
            return 1;
        }
    }
    return 0;
}

/* One Step: handles ., .., @abbrev, axis::, and a bare NodeTest, plus predicates. */
static int32_t parse_step(parser *ps) {
    lexer *lx = &ps->lx;
    if (lx->kind == TK_DOT) {
        lex_next(lx);
        int32_t step = xn_new(ps->p, XN_STEP);
        if (step < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[step].axis = AX_SELF;
        ps->p->nodes[step].test = NT_NODE;
        return step;
    }
    if (lx->kind == TK_DOTDOT) {
        lex_next(lx);
        int32_t step = xn_new(ps->p, XN_STEP);
        if (step < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[step].axis = AX_PARENT;
        ps->p->nodes[step].test = NT_NODE;
        return step;
    }
    int32_t step = xn_new(ps->p, XN_STEP);
    if (step < 0) {                /* GCOVR_EXCL_BR_LINE: alloc */
        fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
        return -1;                 /* GCOVR_EXCL_LINE */
    }
    enum xp_axis axis = AX_CHILD;
    if (lx->kind == TK_AT) {
        lex_next(lx);
        axis = AX_ATTRIBUTE;
    } else if (lx->kind == TK_NAME) {
        /* an AxisName immediately followed by '::' */
        Py_ssize_t save = lx->pos;
        while (save + 1 < lx->len && xp_is_space(lx->src[save])) {
            save++;
        }
        enum xp_axis named;
        if (save + 1 < lx->len && lx->src[save] == ':' && lx->src[save + 1] == ':' && axis_from_name(lx, &named)) {
            axis = named;
            lex_next(lx); /* the axis name */
            expect(ps, TK_COLONCOLON, "expected '::'");
        }
    }
    ps->p->nodes[step].axis = (uint8_t)axis;
    parse_node_test(ps, step);
    ps->p->nodes[step].a = parse_predicates(ps);
    return step;
}

static int starts_step(tok_kind k) {
    return k == TK_NAME || k == TK_STAR || k == TK_AT || k == TK_DOT || k == TK_DOTDOT;
}

/* A RelativeLocationPath chained onto an existing head step list (after / or //).
   Appends to *tail; inserts a synthetic descendant-or-self::node() for //. */
static void parse_relative_tail(parser *ps, int32_t *head, int32_t *tail, int dslash) {
    if (dslash) {
        int32_t ds = xn_new(ps->p, XN_STEP);
        if (ds < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return;   /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[ds].axis = AX_DESCENDANT_OR_SELF;
        ps->p->nodes[ds].test = NT_NODE;
        if (*head < 0) {
            *head = ds;
        } else {
            ps->p->nodes[*tail].next = ds;
        }
        *tail = ds;
    }
    int32_t step = parse_step(ps);
    if (step < 0) { /* GCOVR_EXCL_BR_LINE: parse_step only returns negative on arena allocation failure */
        return;     /* GCOVR_EXCL_LINE */
    }
    if (*head < 0) {
        *head = step;
    } else {
        ps->p->nodes[*tail].next = step;
    }
    *tail = step;
}

/* LocationPath / PathExpr without a leading FilterExpr. */
static int32_t parse_location_path(parser *ps) {
    int32_t path = xn_new(ps->p, XN_PATH);
    if (path < 0) {                /* GCOVR_EXCL_BR_LINE: alloc */
        fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
        return -1;                 /* GCOVR_EXCL_LINE */
    }
    int32_t head = -1;
    int32_t tail = -1;
    if (ps->lx.kind == TK_SLASH) {
        ps->p->nodes[path].absolute = 1;
        lex_next(&ps->lx);
        if (starts_step(ps->lx.kind)) {
            parse_relative_tail(ps, &head, &tail, 0);
        }
    } else if (ps->lx.kind == TK_DSLASH) {
        ps->p->nodes[path].absolute = 1;
        lex_next(&ps->lx);
        parse_relative_tail(ps, &head, &tail, 1);
    } else {
        parse_relative_tail(ps, &head, &tail, 0);
    }
    while ((ps->lx.kind == TK_SLASH || ps->lx.kind == TK_DSLASH)) {
        int dslash = ps->lx.kind == TK_DSLASH;
        lex_next(&ps->lx);
        parse_relative_tail(ps, &head, &tail, dslash);
    }
    ps->p->nodes[path].a = head;
    ps->p->nodes[path].b = -1;
    return path;
}

/* PrimaryExpr: literal, number, ( expr ), function call. */
static int32_t parse_primary(parser *ps) {
    lexer *lx = &ps->lx;
    if (lx->kind == TK_LPAREN) {
        lex_next(lx);
        int32_t inner = parse_expr(ps);
        expect(ps, TK_RPAREN, "expected ')'");
        return inner;
    }
    if (lx->kind == TK_LITERAL) {
        int32_t lit = xn_new(ps->p, XN_LIT);
        if (lit < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1; /* GCOVR_EXCL_LINE */
        }
        if (copy_text(ps->p, lit, lx->tstart, lx->tlen) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            fail(ps, "out of memory");                         /* GCOVR_EXCL_LINE */
        }
        lex_next(lx);
        return lit;
    }
    if (lx->kind == TK_NUM) {
        int32_t num = xn_new(ps->p, XN_NUM);
        if (num < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1; /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[num].num = lx->num;
        lex_next(lx);
        return num;
    }
    if (lx->kind ==
        TK_NAME) { /* GCOVR_EXCL_BR_LINE: starts_filter() guarantees a NAME once the other primaries are ruled out */
        int32_t fn = xn_new(ps->p, XN_FUNC);
        if (fn < 0) {                  /* GCOVR_EXCL_BR_LINE: alloc */
            fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
            return -1;                 /* GCOVR_EXCL_LINE */
        }
        if (copy_text(ps->p, fn, lx->tstart, lx->tlen) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            fail(ps, "out of memory");                        /* GCOVR_EXCL_LINE */
        }
        lex_next(lx);
        expect(ps, TK_LPAREN, "expected '(' after function name");
        int32_t arg_head = -1;
        int32_t arg_tail = -1;
        if (lx->kind != TK_RPAREN) {
            for (;;) {
                int32_t arg = parse_expr(ps);
                if (arg_head < 0) {
                    arg_head = arg;
                } else {
                    ps->p->nodes[arg_tail].next = arg;
                }
                arg_tail = arg;
                if (!accept(ps, TK_COMMA)) {
                    break;
                }
            }
        }
        expect(ps, TK_RPAREN, "expected ')'");
        ps->p->nodes[fn].a = arg_head;
        return fn;
    }
    /* GCOVR_EXCL_START: parse_primary is only entered through starts_filter(), which
       guarantees the current token starts a primary, so this is defensive. */
    fail(ps, "expected an expression");
    return -1;
    /* GCOVR_EXCL_STOP */
}

/* A FilterExpr begins with a literal, number, '(', or a function call (a NAME
   immediately before '(' that is neither an axis name nor a kind test). Anything
   else begins a LocationPath. */
static int starts_filter(parser *ps) {
    tok_kind k = ps->lx.kind;
    if (k == TK_LITERAL || k == TK_NUM || k == TK_LPAREN) {
        return 1;
    }
    if (k != TK_NAME) {
        return 0;
    }
    Py_ssize_t save = ps->lx.pos;
    while (save < ps->lx.len && xp_is_space(ps->lx.src[save])) {
        save++;
    }
    /* a name followed by '(' cannot also be followed by '::', so paren already
       excludes an axis; only the kind tests need ruling out */
    int paren = save < ps->lx.len && ps->lx.src[save] == '(';
    int kind_test = xp_name_eq(&ps->lx, "node") || xp_name_eq(&ps->lx, "text") || xp_name_eq(&ps->lx, "comment") ||
                    xp_name_eq(&ps->lx, "processing-instruction");
    return paren && !kind_test;
}

/* FilterExpr: PrimaryExpr Predicate*, optionally continuing a PathExpr with /steps.
   Filter predicates apply to the whole node-set (so `(//a)[1]` differs from `//a[1]`)
   and are kept on an XN_FILTER node, distinct from a step's per-context predicates. */
static int32_t parse_filter_or_path(parser *ps) {
    if (!starts_filter(ps)) {
        return parse_location_path(ps);
    }
    int32_t primary = parse_primary(ps);
    int32_t preds = parse_predicates(ps);
    int32_t base = primary;
    if (preds >= 0) {
        int32_t filter = xn_new(ps->p, XN_FILTER);
        if (filter < 0) {              /* GCOVR_EXCL_BR_LINE: alloc */
            fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
            return -1;                 /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[filter].a = primary;
        ps->p->nodes[filter].b = preds;
        base = filter;
    }
    if (ps->lx.kind != TK_SLASH && ps->lx.kind != TK_DSLASH) {
        return base;
    }
    int32_t path = xn_new(ps->p, XN_PATH);
    if (path < 0) {                /* GCOVR_EXCL_BR_LINE: alloc */
        fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
        return -1;                 /* GCOVR_EXCL_LINE */
    }
    ps->p->nodes[path].b = base;
    int32_t head = -1;
    int32_t tail = -1;
    while ((ps->lx.kind == TK_SLASH || ps->lx.kind == TK_DSLASH)) {
        int dslash = ps->lx.kind == TK_DSLASH;
        lex_next(&ps->lx);
        parse_relative_tail(ps, &head, &tail, dslash);
    }
    ps->p->nodes[path].a = head;
    return path;
}

static int32_t parse_union(parser *ps) {
    int32_t left = parse_filter_or_path(ps);
    while (ps->lx.kind == TK_PIPE) {
        lex_next(&ps->lx);
        int32_t right = parse_filter_or_path(ps);
        int32_t u = xn_new(ps->p, XN_UNION);
        if (u < 0) {   /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1; /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[u].a = left;
        ps->p->nodes[u].b = right;
        left = u;
    }
    return left;
}

static int32_t parse_unary(parser *ps) {
    if (ps->lx.kind == TK_MINUS) {
        lex_next(&ps->lx);
        int32_t operand = parse_unary(ps);
        int32_t neg = xn_new(ps->p, XN_NEG);
        if (neg < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1; /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[neg].a = operand;
        return neg;
    }
    return parse_union(ps);
}

static int32_t parse_multiplicative(parser *ps) {
    int32_t left = parse_unary(ps);
    for (;;) {
        enum xn_kind k;
        if (ps->lx.kind == TK_STAR) {
            k = XN_MUL;
        } else if (ps->lx.kind == TK_DIV) {
            k = XN_DIV;
        } else if (ps->lx.kind == TK_MOD) {
            k = XN_MOD;
        } else {
            break;
        }
        lex_next(&ps->lx);
        int32_t right = parse_unary(ps);
        int32_t node = xn_new(ps->p, k);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[node].a = left;
        ps->p->nodes[node].b = right;
        left = node;
    }
    return left;
}

static int32_t parse_additive(parser *ps) {
    int32_t left = parse_multiplicative(ps);
    for (;;) {
        enum xn_kind k;
        if (ps->lx.kind == TK_PLUS) {
            k = XN_ADD;
        } else if (ps->lx.kind == TK_MINUS) {
            k = XN_SUB;
        } else {
            break;
        }
        lex_next(&ps->lx);
        int32_t right = parse_multiplicative(ps);
        int32_t node = xn_new(ps->p, k);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[node].a = left;
        ps->p->nodes[node].b = right;
        left = node;
    }
    return left;
}

static int32_t parse_relational(parser *ps) {
    int32_t left = parse_additive(ps);
    for (;;) {
        enum xn_kind k;
        if (ps->lx.kind == TK_LT) {
            k = XN_LT;
        } else if (ps->lx.kind == TK_LE) {
            k = XN_LE;
        } else if (ps->lx.kind == TK_GT) {
            k = XN_GT;
        } else if (ps->lx.kind == TK_GE) {
            k = XN_GE;
        } else {
            break;
        }
        lex_next(&ps->lx);
        int32_t right = parse_additive(ps);
        int32_t node = xn_new(ps->p, k);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[node].a = left;
        ps->p->nodes[node].b = right;
        left = node;
    }
    return left;
}

static int32_t parse_equality(parser *ps) {
    int32_t left = parse_relational(ps);
    for (;;) {
        enum xn_kind k;
        if (ps->lx.kind == TK_EQ) {
            k = XN_EQ;
        } else if (ps->lx.kind == TK_NE) {
            k = XN_NE;
        } else {
            break;
        }
        lex_next(&ps->lx);
        int32_t right = parse_relational(ps);
        int32_t node = xn_new(ps->p, k);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[node].a = left;
        ps->p->nodes[node].b = right;
        left = node;
    }
    return left;
}

static int32_t parse_and(parser *ps) {
    int32_t left = parse_equality(ps);
    while (ps->lx.kind == TK_AND) {
        lex_next(&ps->lx);
        int32_t right = parse_equality(ps);
        int32_t node = xn_new(ps->p, XN_AND);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[node].a = left;
        ps->p->nodes[node].b = right;
        left = node;
    }
    return left;
}

static int32_t parse_expr(parser *ps) {
    int32_t left = parse_and(ps);
    while (ps->lx.kind == TK_OR) {
        lex_next(&ps->lx);
        int32_t right = parse_and(ps);
        int32_t node = xn_new(ps->p, XN_OR);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->p->nodes[node].a = left;
        ps->p->nodes[node].b = right;
        left = node;
    }
    return left;
}

/* ---------------------------------------------------------- public API */

xp_program *xp_compile(const Py_UCS4 *src, Py_ssize_t len, char *errbuf, size_t errlen) {
    xp_program *p = PyMem_Malloc(sizeof(*p));
    if (p == NULL) {                               /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        snprintf(errbuf, errlen, "out of memory"); /* GCOVR_EXCL_LINE */
        return NULL;                               /* GCOVR_EXCL_LINE */
    }
    p->nodes = NULL;
    p->count = 0;
    p->cap = 0;
    p->root = -1;
    parser ps = {0};
    ps.p = p;
    ps.lx.src = src;
    ps.lx.len = len;
    ps.lx.op_context = 0;
    lex_next(&ps.lx);
    if (ps.lx.error) {
        fail(&ps, "invalid character in expression");
    }
    p->root = parse_expr(&ps);
    if (ps.lx.error) {
        /* a stray character that made the lexer stop where the parser also stopped
           (e.g. a lone '!') would otherwise look like a clean end of input */
        fail(&ps, "invalid character in expression");
    }
    if (!ps.failed && ps.lx.kind != TK_EOF) {
        fail(&ps, "unexpected trailing tokens");
    }
    /* root < 0 and a NULL message only arise from an arena allocation failure that
       did not record a message, so those branches cannot be forced from a test */
    if (ps.failed || p->root < 0) {                                                   /* GCOVR_EXCL_BR_LINE */
        snprintf(errbuf, errlen, "%s", ps.msg ? ps.msg : "invalid XPath expression"); /* GCOVR_EXCL_BR_LINE */
        xp_free(p);
        return NULL;
    }
    return p;
}

void xp_free(xp_program *prog) {
    if (prog == NULL) { /* GCOVR_EXCL_BR_LINE: callers never pass NULL */
        return;         /* GCOVR_EXCL_LINE */
    }
    for (int32_t i = 0; i < prog->count; i++) {
        PyMem_Free(prog->nodes[i].str);
    }
    PyMem_Free(prog->nodes);
    PyMem_Free(prog);
}

/* ------------------------------------------------------------- AST dump */

typedef struct {
    Py_UCS4 *buf;
    Py_ssize_t len;
    Py_ssize_t cap;
    int failed;
} dumper;

static void dput(dumper *d, Py_UCS4 c) {
    if (d->len == d->cap) {
        Py_ssize_t cap = d->cap ? d->cap * 2 : 64;
        Py_UCS4 *grown = PyMem_Realloc(d->buf, (size_t)cap * sizeof(Py_UCS4));
        if (grown == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
            d->failed = 1;   /* GCOVR_EXCL_LINE */
            return;          /* GCOVR_EXCL_LINE */
        }
        d->buf = grown;
        d->cap = cap;
    }
    d->buf[d->len++] = c;
}

static void dputs(dumper *d, const char *s) {
    for (; *s; s++) {
        dput(d, (Py_UCS4)(unsigned char)*s);
    }
}

static void dput_run(dumper *d, const Py_UCS4 *s, Py_ssize_t n) {
    for (Py_ssize_t i = 0; i < n; i++) {
        dput(d, s[i]);
    }
}

static void dput_num(dumper *d, double v) {
    char tmp[64];
    if (v == (double)(long)v && fabs(v) < 1e15) {
        snprintf(tmp, sizeof(tmp), "%ld", (long)v);
    } else {
        snprintf(tmp, sizeof(tmp), "%g", v);
    }
    dputs(d, tmp);
}

static const char *axis_name(uint8_t axis) {
    switch (axis) {
    case AX_CHILD:
        return "child";
    case AX_DESCENDANT:
        return "descendant";
    case AX_DESCENDANT_OR_SELF:
        return "descendant-or-self";
    case AX_ATTRIBUTE:
        return "attribute";
    case AX_SELF:
        return "self";
    case AX_PARENT:
        return "parent";
    case AX_ANCESTOR:
        return "ancestor";
    case AX_ANCESTOR_OR_SELF:
        return "ancestor-or-self";
    case AX_FOLLOWING_SIBLING:
        return "following-sibling";
    case AX_PRECEDING_SIBLING:
        return "preceding-sibling";
    case AX_FOLLOWING:
        return "following";
    case AX_PRECEDING:
        return "preceding";
    default: /* AX_NAMESPACE */
        return "namespace";
    }
}

static void dump_node(dumper *d, const xp_program *p, int32_t idx);

static void dump_step(dumper *d, const xp_program *p, int32_t idx) {
    const xn *n = &p->nodes[idx];
    dputs(d, "(step ");
    dputs(d, axis_name(n->axis));
    dput(d, ' ');
    switch (n->test) {
    case NT_NAME:
        dputs(d, "name '");
        dput_run(d, n->str, n->str_len);
        dput(d, '\'');
        break;
    case NT_STAR:
        dputs(d, "*");
        break;
    case NT_NODE:
        dputs(d, "node()");
        break;
    case NT_TEXT:
        dputs(d, "text()");
        break;
    case NT_COMMENT:
        dputs(d, "comment()");
        break;
    default: /* NT_PI */
        dputs(d, "pi(");
        if (n->str != NULL) {
            dput(d, '\'');
            dput_run(d, n->str, n->str_len);
            dput(d, '\'');
        }
        dput(d, ')');
        break;
    }
    for (int32_t pr = n->a; pr >= 0; pr = p->nodes[pr].next) {
        dputs(d, " (pred ");
        dump_node(d, p, p->nodes[pr].a);
        dput(d, ')');
    }
    dput(d, ')');
}

static void dump_node(dumper *d, const xp_program *p, int32_t idx) {
    const xn *n = &p->nodes[idx];
    static const char *binop[] = {"or", "and", "=", "!=", "<", "<=", ">", ">=", "+", "-", "*", "div", "mod"};
    switch (n->kind) {
    case XN_OR:
    case XN_AND:
    case XN_EQ:
    case XN_NE:
    case XN_LT:
    case XN_LE:
    case XN_GT:
    case XN_GE:
    case XN_ADD:
    case XN_SUB:
    case XN_MUL:
    case XN_DIV:
    case XN_MOD:
        dput(d, '(');
        dputs(d, binop[n->kind - XN_OR]);
        dput(d, ' ');
        dump_node(d, p, n->a);
        dput(d, ' ');
        dump_node(d, p, n->b);
        dput(d, ')');
        break;
    case XN_NEG:
        dputs(d, "(neg ");
        dump_node(d, p, n->a);
        dput(d, ')');
        break;
    case XN_UNION:
        dputs(d, "(union ");
        dump_node(d, p, n->a);
        dput(d, ' ');
        dump_node(d, p, n->b);
        dput(d, ')');
        break;
    case XN_NUM:
        dputs(d, "(num ");
        dput_num(d, n->num);
        dput(d, ')');
        break;
    case XN_LIT:
        dputs(d, "(lit '");
        dput_run(d, n->str, n->str_len);
        dputs(d, "')");
        break;
    case XN_FUNC:
        dputs(d, "(call '");
        dput_run(d, n->str, n->str_len);
        dput(d, '\'');
        for (int32_t arg = n->a; arg >= 0; arg = p->nodes[arg].next) {
            dput(d, ' ');
            dump_node(d, p, arg);
        }
        dput(d, ')');
        break;
    case XN_FILTER:
        dputs(d, "(filter ");
        dump_node(d, p, n->a);
        for (int32_t pr = n->b; pr >= 0; pr = p->nodes[pr].next) {
            dputs(d, " (pred ");
            dump_node(d, p, p->nodes[pr].a);
            dput(d, ')');
        }
        dput(d, ')');
        break;
    default: /* XN_PATH */
        dputs(d, "(path ");
        dputs(d, n->absolute ? "abs" : "rel");
        if (n->b >= 0) {
            dputs(d, " (from ");
            dump_node(d, p, n->b);
            dput(d, ')');
        }
        for (int32_t st = n->a; st >= 0; st = p->nodes[st].next) {
            dput(d, ' ');
            dump_step(d, p, st);
        }
        dput(d, ')');
        break;
    }
}

Py_UCS4 *xp_dump(const xp_program *prog, Py_ssize_t *out_len) {
    dumper d = {0};
    dump_node(&d, prog, prog->root);
    if (d.failed) {        /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        PyMem_Free(d.buf); /* GCOVR_EXCL_LINE */
        return NULL;       /* GCOVR_EXCL_LINE */
    }
    if (d.buf == NULL) {                       /* GCOVR_EXCL_BR_LINE: the root always emits at least "()" */
        d.buf = PyMem_Malloc(sizeof(Py_UCS4)); /* GCOVR_EXCL_LINE */
    }
    *out_len = d.len;
    return d.buf;
}

/* --------------------------------------------------- Python test hook */

PyObject *turbohtml_xpath_parse(PyObject *Py_UNUSED(module), PyObject *arg) {
    if (!PyUnicode_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "xpath expression must be a str");
        return NULL;
    }
    Py_ssize_t len = PyUnicode_GET_LENGTH(arg);
    Py_UCS4 *src = PyUnicode_AsUCS4Copy(arg);
    if (src == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;   /* GCOVR_EXCL_LINE */
    }
    char err[128];
    xp_program *prog = xp_compile(src, len, err, sizeof(err));
    PyMem_Free(src);
    if (prog == NULL) {
        PyErr_SetString(PyExc_ValueError, err);
        return NULL;
    }
    Py_ssize_t dlen;
    Py_UCS4 *dump = xp_dump(prog, &dlen);
    xp_free(prog);
    if (dump == NULL) {          /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        return PyErr_NoMemory(); /* GCOVR_EXCL_LINE */
    }
    PyObject *result = PyUnicode_FromKindAndData(PyUnicode_4BYTE_KIND, dump, dlen);
    PyMem_Free(dump);
    return result;
}
