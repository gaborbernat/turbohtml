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
#include "treebuilder.h"
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
    int32_t first;    /* first child / operand */
    int32_t second;   /* second child */
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
static int32_t xn_new(xp_program *prog, enum xn_kind kind) {
    if (prog->count == prog->cap) {
        int32_t cap = prog->cap ? prog->cap * 2 : 16;
        xn *grown = PyMem_Realloc(prog->nodes, (size_t)cap * sizeof(xn));
        if (grown == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return -1;       /* GCOVR_EXCL_LINE */
        }
        prog->nodes = grown;
        prog->cap = cap;
    }
    int32_t idx = prog->count++;
    xn *node = &prog->nodes[idx];
    memset(node, 0, sizeof(*node));
    node->kind = (uint8_t)kind;
    node->first = node->second = node->next = -1;
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

static int xp_is_name_start(Py_UCS4 ch) {
    return (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || ch == '_' || ch >= 0x80;
}

static int xp_is_name_char(Py_UCS4 ch) {
    return xp_is_name_start(ch) || (ch >= '0' && ch <= '9') || ch == '-' || ch == '.';
}

static int xp_is_space(Py_UCS4 ch) {
    return ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n';
}

static int xp_name_eq(const lexer *lx, const char *kw) {
    Py_ssize_t index = 0;
    for (; kw[index] != '\0'; index++) {
        if (index >= lx->tlen || lx->tstart[index] != (Py_UCS4)(unsigned char)kw[index]) {
            return 0;
        }
    }
    return index == lx->tlen;
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
    Py_UCS4 ch = lx->src[lx->pos];
    Py_UCS4 peek = lx->pos + 1 < lx->len ? lx->src[lx->pos + 1] : 0;
    switch (ch) {
    case '/':
        lx->pos += peek == '/' ? 2 : 1;
        lx->kind = peek == '/' ? TK_DSLASH : TK_SLASH;
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
        if (peek == '=') {
            lx->pos += 2;
            lx->kind = TK_NE;
        } else {
            lx->error = 1;
            lx->kind = TK_EOF;
        }
        break;
    case '<':
        lx->pos += peek == '=' ? 2 : 1;
        lx->kind = peek == '=' ? TK_LE : TK_LT;
        break;
    case '>':
        lx->pos += peek == '=' ? 2 : 1;
        lx->kind = peek == '=' ? TK_GE : TK_GT;
        break;
    case ':':
        if (peek == ':') {
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
        while (lx->pos < lx->len && lx->src[lx->pos] != ch) {
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
        if (peek == '.') {
            lx->pos += 2;
            lx->kind = TK_DOTDOT;
        } else if (peek >= '0' && peek <= '9') {
            goto number;
        } else {
            lx->pos++;
            lx->kind = TK_DOT;
        }
        break;
    default:
        if (ch >= '0' && ch <= '9') {
            goto number;
        }
        if (xp_is_name_start(ch)) {
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
        for (Py_ssize_t index = start; index < lx->pos; index++) {
            Py_UCS4 ch = lx->src[index];
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
    xp_program *prog;
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
static int copy_text(xp_program *prog, int32_t idx, const Py_UCS4 *src, Py_ssize_t len) {
    Py_UCS4 *buf = PyMem_Malloc((size_t)len * sizeof(Py_UCS4));
    if (buf == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;     /* GCOVR_EXCL_LINE */
    }
    memcpy(buf, src, (size_t)len * sizeof(Py_UCS4));
    prog->nodes[idx].str = buf;
    prog->nodes[idx].str_len = len;
    return 0;
}

/* A NodeTest after an axis has been chosen; fills test/str on the step node. */
static void parse_node_test(parser *ps, int32_t step) {
    lexer *lx = &ps->lx;
    if (lx->kind == TK_STAR) {
        ps->prog->nodes[step].test = NT_STAR;
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
        ps->prog->nodes[step].test = (uint8_t)(is_node ? NT_NODE : is_text ? NT_TEXT : is_comment ? NT_COMMENT : NT_PI);
        lex_next(lx); /* the name */
        expect(ps, TK_LPAREN, "expected '('");
        if (is_pi && lx->kind == TK_LITERAL) {
            if (copy_text(ps->prog, step, lx->tstart, lx->tlen) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                fail(ps, "out of memory");                             /* GCOVR_EXCL_LINE */
            }
            lex_next(lx);
        }
        expect(ps, TK_RPAREN, "expected ')'");
        return;
    }
    ps->prog->nodes[step].test = NT_NAME;
    if (copy_text(ps->prog, step, lx->tstart, lx->tlen) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
        fail(ps, "out of memory");                             /* GCOVR_EXCL_LINE */
    }
    lex_next(lx);
}

/* Parse the predicate list onto a step (or filter), returning the head index. */
static int32_t parse_predicates(parser *ps) {
    int32_t head = -1;
    int32_t tail = -1;
    while (ps->lx.kind == TK_LBRACK) {
        lex_next(&ps->lx);
        int32_t pred = xn_new(ps->prog, XN_PRED);
        if (pred < 0) {                /* GCOVR_EXCL_BR_LINE: alloc */
            fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
            return head;               /* GCOVR_EXCL_LINE */
        }
        int32_t expr = parse_expr(ps);
        ps->prog->nodes[pred].first = expr;
        expect(ps, TK_RBRACK, "expected ']'");
        if (head < 0) {
            head = pred;
        } else {
            ps->prog->nodes[tail].next = pred;
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
    for (size_t index = 0; index < sizeof(table) / sizeof(table[0]); index++) {
        if (xp_name_eq(lx, table[index].name)) {
            *out = table[index].axis;
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
        int32_t step = xn_new(ps->prog, XN_STEP);
        if (step < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[step].axis = AX_SELF;
        ps->prog->nodes[step].test = NT_NODE;
        return step;
    }
    if (lx->kind == TK_DOTDOT) {
        lex_next(lx);
        int32_t step = xn_new(ps->prog, XN_STEP);
        if (step < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[step].axis = AX_PARENT;
        ps->prog->nodes[step].test = NT_NODE;
        return step;
    }
    int32_t step = xn_new(ps->prog, XN_STEP);
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
    ps->prog->nodes[step].axis = (uint8_t)axis;
    parse_node_test(ps, step);
    ps->prog->nodes[step].first = parse_predicates(ps);
    return step;
}

static int starts_step(tok_kind kind) {
    return kind == TK_NAME || kind == TK_STAR || kind == TK_AT || kind == TK_DOT || kind == TK_DOTDOT;
}

/* A RelativeLocationPath chained onto an existing head step list (after / or //).
   Appends to *tail; inserts a synthetic descendant-or-self::node() for //. */
static void parse_relative_tail(parser *ps, int32_t *head, int32_t *tail, int dslash) {
    if (dslash) {
        int32_t ds = xn_new(ps->prog, XN_STEP);
        if (ds < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return;   /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[ds].axis = AX_DESCENDANT_OR_SELF;
        ps->prog->nodes[ds].test = NT_NODE;
        if (*head < 0) {
            *head = ds;
        } else {
            ps->prog->nodes[*tail].next = ds;
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
        ps->prog->nodes[*tail].next = step;
    }
    *tail = step;
}

/* LocationPath / PathExpr without a leading FilterExpr. */
static int32_t parse_location_path(parser *ps) {
    int32_t path = xn_new(ps->prog, XN_PATH);
    if (path < 0) {                /* GCOVR_EXCL_BR_LINE: alloc */
        fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
        return -1;                 /* GCOVR_EXCL_LINE */
    }
    int32_t head = -1;
    int32_t tail = -1;
    if (ps->lx.kind == TK_SLASH) {
        ps->prog->nodes[path].absolute = 1;
        lex_next(&ps->lx);
        if (starts_step(ps->lx.kind)) {
            parse_relative_tail(ps, &head, &tail, 0);
        }
    } else if (ps->lx.kind == TK_DSLASH) {
        ps->prog->nodes[path].absolute = 1;
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
    ps->prog->nodes[path].first = head;
    ps->prog->nodes[path].second = -1;
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
        int32_t lit = xn_new(ps->prog, XN_LIT);
        if (lit < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1; /* GCOVR_EXCL_LINE */
        }
        if (copy_text(ps->prog, lit, lx->tstart, lx->tlen) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            fail(ps, "out of memory");                            /* GCOVR_EXCL_LINE */
        }
        lex_next(lx);
        return lit;
    }
    if (lx->kind == TK_NUM) {
        int32_t num = xn_new(ps->prog, XN_NUM);
        if (num < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1; /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[num].num = lx->num;
        lex_next(lx);
        return num;
    }
    /* The only remaining primary is a FunctionCall: starts_filter() guarantees a
       NAME here once '(', a literal, and a number have been ruled out above. */
    int32_t fn = xn_new(ps->prog, XN_FUNC);
    if (fn < 0) {                  /* GCOVR_EXCL_BR_LINE: alloc */
        fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
        return -1;                 /* GCOVR_EXCL_LINE */
    }
    if (copy_text(ps->prog, fn, lx->tstart, lx->tlen) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
        fail(ps, "out of memory");                           /* GCOVR_EXCL_LINE */
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
                ps->prog->nodes[arg_tail].next = arg;
            }
            arg_tail = arg;
            if (!accept(ps, TK_COMMA)) {
                break;
            }
        }
    }
    expect(ps, TK_RPAREN, "expected ')'");
    ps->prog->nodes[fn].first = arg_head;
    return fn;
}

/* A FilterExpr begins with a literal, number, '(', or a function call (a NAME
   immediately before '(' that is neither an axis name nor a kind test). Anything
   else begins a LocationPath. */
static int starts_filter(parser *ps) {
    tok_kind kind = ps->lx.kind;
    if (kind == TK_LITERAL || kind == TK_NUM || kind == TK_LPAREN) {
        return 1;
    }
    if (kind != TK_NAME) {
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
        int32_t filter = xn_new(ps->prog, XN_FILTER);
        if (filter < 0) {              /* GCOVR_EXCL_BR_LINE: alloc */
            fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
            return -1;                 /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[filter].first = primary;
        ps->prog->nodes[filter].second = preds;
        base = filter;
    }
    if (ps->lx.kind != TK_SLASH && ps->lx.kind != TK_DSLASH) {
        return base;
    }
    int32_t path = xn_new(ps->prog, XN_PATH);
    if (path < 0) {                /* GCOVR_EXCL_BR_LINE: alloc */
        fail(ps, "out of memory"); /* GCOVR_EXCL_LINE */
        return -1;                 /* GCOVR_EXCL_LINE */
    }
    ps->prog->nodes[path].second = base;
    int32_t head = -1;
    int32_t tail = -1;
    while ((ps->lx.kind == TK_SLASH || ps->lx.kind == TK_DSLASH)) {
        int dslash = ps->lx.kind == TK_DSLASH;
        lex_next(&ps->lx);
        parse_relative_tail(ps, &head, &tail, dslash);
    }
    ps->prog->nodes[path].first = head;
    return path;
}

static int32_t parse_union(parser *ps) {
    int32_t left = parse_filter_or_path(ps);
    while (ps->lx.kind == TK_PIPE) {
        lex_next(&ps->lx);
        int32_t right = parse_filter_or_path(ps);
        int32_t union_node = xn_new(ps->prog, XN_UNION);
        if (union_node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;        /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[union_node].first = left;
        ps->prog->nodes[union_node].second = right;
        left = union_node;
    }
    return left;
}

static int32_t parse_unary(parser *ps) {
    if (ps->lx.kind == TK_MINUS) {
        lex_next(&ps->lx);
        int32_t operand = parse_unary(ps);
        int32_t neg = xn_new(ps->prog, XN_NEG);
        if (neg < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1; /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[neg].first = operand;
        return neg;
    }
    return parse_union(ps);
}

static int32_t parse_multiplicative(parser *ps) {
    int32_t left = parse_unary(ps);
    for (;;) {
        enum xn_kind op;
        if (ps->lx.kind == TK_STAR) {
            op = XN_MUL;
        } else if (ps->lx.kind == TK_DIV) {
            op = XN_DIV;
        } else if (ps->lx.kind == TK_MOD) {
            op = XN_MOD;
        } else {
            break;
        }
        lex_next(&ps->lx);
        int32_t right = parse_unary(ps);
        int32_t node = xn_new(ps->prog, op);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[node].first = left;
        ps->prog->nodes[node].second = right;
        left = node;
    }
    return left;
}

static int32_t parse_additive(parser *ps) {
    int32_t left = parse_multiplicative(ps);
    for (;;) {
        enum xn_kind op;
        if (ps->lx.kind == TK_PLUS) {
            op = XN_ADD;
        } else if (ps->lx.kind == TK_MINUS) {
            op = XN_SUB;
        } else {
            break;
        }
        lex_next(&ps->lx);
        int32_t right = parse_multiplicative(ps);
        int32_t node = xn_new(ps->prog, op);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[node].first = left;
        ps->prog->nodes[node].second = right;
        left = node;
    }
    return left;
}

static int32_t parse_relational(parser *ps) {
    int32_t left = parse_additive(ps);
    for (;;) {
        enum xn_kind op;
        if (ps->lx.kind == TK_LT) {
            op = XN_LT;
        } else if (ps->lx.kind == TK_LE) {
            op = XN_LE;
        } else if (ps->lx.kind == TK_GT) {
            op = XN_GT;
        } else if (ps->lx.kind == TK_GE) {
            op = XN_GE;
        } else {
            break;
        }
        lex_next(&ps->lx);
        int32_t right = parse_additive(ps);
        int32_t node = xn_new(ps->prog, op);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[node].first = left;
        ps->prog->nodes[node].second = right;
        left = node;
    }
    return left;
}

static int32_t parse_equality(parser *ps) {
    int32_t left = parse_relational(ps);
    for (;;) {
        enum xn_kind op;
        if (ps->lx.kind == TK_EQ) {
            op = XN_EQ;
        } else if (ps->lx.kind == TK_NE) {
            op = XN_NE;
        } else {
            break;
        }
        lex_next(&ps->lx);
        int32_t right = parse_relational(ps);
        int32_t node = xn_new(ps->prog, op);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[node].first = left;
        ps->prog->nodes[node].second = right;
        left = node;
    }
    return left;
}

static int32_t parse_and(parser *ps) {
    int32_t left = parse_equality(ps);
    while (ps->lx.kind == TK_AND) {
        lex_next(&ps->lx);
        int32_t right = parse_equality(ps);
        int32_t node = xn_new(ps->prog, XN_AND);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[node].first = left;
        ps->prog->nodes[node].second = right;
        left = node;
    }
    return left;
}

static int32_t parse_expr(parser *ps) {
    int32_t left = parse_and(ps);
    while (ps->lx.kind == TK_OR) {
        lex_next(&ps->lx);
        int32_t right = parse_and(ps);
        int32_t node = xn_new(ps->prog, XN_OR);
        if (node < 0) { /* GCOVR_EXCL_BR_LINE: arena allocation failure cannot be forced */
            return -1;  /* GCOVR_EXCL_LINE */
        }
        ps->prog->nodes[node].first = left;
        ps->prog->nodes[node].second = right;
        left = node;
    }
    return left;
}

/* ---------------------------------------------------------- public API */

xp_program *xp_compile(const Py_UCS4 *src, Py_ssize_t len, char *errbuf, size_t errlen) {
    xp_program *prog = PyMem_Malloc(sizeof(*prog));
    if (prog == NULL) {                            /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        snprintf(errbuf, errlen, "out of memory"); /* GCOVR_EXCL_LINE */
        return NULL;                               /* GCOVR_EXCL_LINE */
    }
    prog->nodes = NULL;
    prog->count = 0;
    prog->cap = 0;
    prog->root = -1;
    parser ps = {0};
    ps.prog = prog;
    ps.lx.src = src;
    ps.lx.len = len;
    ps.lx.op_context = 0;
    lex_next(&ps.lx);
    if (ps.lx.error) {
        fail(&ps, "invalid character in expression");
    }
    prog->root = parse_expr(&ps);
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
    if (ps.failed || prog->root < 0) {                                                /* GCOVR_EXCL_BR_LINE */
        snprintf(errbuf, errlen, "%s", ps.msg ? ps.msg : "invalid XPath expression"); /* GCOVR_EXCL_BR_LINE */
        xp_free(prog);
        return NULL;
    }
    return prog;
}

void xp_free(xp_program *prog) {
    if (prog == NULL) { /* GCOVR_EXCL_BR_LINE: callers never pass NULL */
        return;         /* GCOVR_EXCL_LINE */
    }
    for (int32_t index = 0; index < prog->count; index++) {
        PyMem_Free(prog->nodes[index].str);
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

static void dput(dumper *out, Py_UCS4 ch) {
    if (out->len == out->cap) {
        Py_ssize_t cap = out->cap ? out->cap * 2 : 64;
        Py_UCS4 *grown = PyMem_Realloc(out->buf, (size_t)cap * sizeof(Py_UCS4));
        if (grown == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
            out->failed = 1; /* GCOVR_EXCL_LINE */
            return;          /* GCOVR_EXCL_LINE */
        }
        out->buf = grown;
        out->cap = cap;
    }
    out->buf[out->len++] = ch;
}

static void dputs(dumper *out, const char *text) {
    for (; *text; text++) {
        dput(out, (Py_UCS4)(unsigned char)*text);
    }
}

static void dput_run(dumper *out, const Py_UCS4 *text, Py_ssize_t count) {
    for (Py_ssize_t index = 0; index < count; index++) {
        dput(out, text[index]);
    }
}

static void dput_num(dumper *out, double value) {
    char tmp[64];
    if (value == (double)(long)value && fabs(value) < 1e15) {
        snprintf(tmp, sizeof(tmp), "%ld", (long)value);
    } else {
        snprintf(tmp, sizeof(tmp), "%g", value);
    }
    dputs(out, tmp);
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

static void dump_node(dumper *d, const xp_program *prog, int32_t idx);

static void dump_step(dumper *out, const xp_program *prog, int32_t idx) {
    const xn *expr = &prog->nodes[idx];
    dputs(out, "(step ");
    dputs(out, axis_name(expr->axis));
    dput(out, ' ');
    switch (expr->test) {
    case NT_NAME:
        dputs(out, "name '");
        dput_run(out, expr->str, expr->str_len);
        dput(out, '\'');
        break;
    case NT_STAR:
        dputs(out, "*");
        break;
    case NT_NODE:
        dputs(out, "node()");
        break;
    case NT_TEXT:
        dputs(out, "text()");
        break;
    case NT_COMMENT:
        dputs(out, "comment()");
        break;
    default: /* NT_PI */
        dputs(out, "pi(");
        if (expr->str != NULL) {
            dput(out, '\'');
            dput_run(out, expr->str, expr->str_len);
            dput(out, '\'');
        }
        dput(out, ')');
        break;
    }
    for (int32_t pr = expr->first; pr >= 0; pr = prog->nodes[pr].next) {
        dputs(out, " (pred ");
        dump_node(out, prog, prog->nodes[pr].first);
        dput(out, ')');
    }
    dput(out, ')');
}

static void dump_node(dumper *out, const xp_program *prog, int32_t idx) {
    const xn *expr = &prog->nodes[idx];
    static const char *binop[] = {"or", "and", "=", "!=", "<", "<=", ">", ">=", "+", "-", "*", "div", "mod"};
    switch (expr->kind) {
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
        dput(out, '(');
        dputs(out, binop[expr->kind - XN_OR]);
        dput(out, ' ');
        dump_node(out, prog, expr->first);
        dput(out, ' ');
        dump_node(out, prog, expr->second);
        dput(out, ')');
        break;
    case XN_NEG:
        dputs(out, "(neg ");
        dump_node(out, prog, expr->first);
        dput(out, ')');
        break;
    case XN_UNION:
        dputs(out, "(union ");
        dump_node(out, prog, expr->first);
        dput(out, ' ');
        dump_node(out, prog, expr->second);
        dput(out, ')');
        break;
    case XN_NUM:
        dputs(out, "(num ");
        dput_num(out, expr->num);
        dput(out, ')');
        break;
    case XN_LIT:
        dputs(out, "(lit '");
        dput_run(out, expr->str, expr->str_len);
        dputs(out, "')");
        break;
    case XN_FUNC:
        dputs(out, "(call '");
        dput_run(out, expr->str, expr->str_len);
        dput(out, '\'');
        for (int32_t arg = expr->first; arg >= 0; arg = prog->nodes[arg].next) {
            dput(out, ' ');
            dump_node(out, prog, arg);
        }
        dput(out, ')');
        break;
    case XN_FILTER:
        dputs(out, "(filter ");
        dump_node(out, prog, expr->first);
        for (int32_t pr = expr->second; pr >= 0; pr = prog->nodes[pr].next) {
            dputs(out, " (pred ");
            dump_node(out, prog, prog->nodes[pr].first);
            dput(out, ')');
        }
        dput(out, ')');
        break;
    default: /* XN_PATH */
        dputs(out, "(path ");
        dputs(out, expr->absolute ? "abs" : "rel");
        if (expr->second >= 0) {
            dputs(out, " (from ");
            dump_node(out, prog, expr->second);
            dput(out, ')');
        }
        for (int32_t st = expr->first; st >= 0; st = prog->nodes[st].next) {
            dput(out, ' ');
            dump_step(out, prog, st);
        }
        dput(out, ')');
        break;
    }
}

Py_UCS4 *xp_dump(const xp_program *prog, Py_ssize_t *out_len) {
    dumper state = {0};
    dump_node(&state, prog, prog->root);
    if (state.failed) {        /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        PyMem_Free(state.buf); /* GCOVR_EXCL_LINE */
        return NULL;           /* GCOVR_EXCL_LINE */
    }
    if (state.buf == NULL) {                       /* GCOVR_EXCL_BR_LINE: the root always emits at least "()" */
        state.buf = PyMem_Malloc(sizeof(Py_UCS4)); /* GCOVR_EXCL_LINE */
    }
    *out_len = state.len;
    return state.buf;
}

/* ---------------------------------------------------------- evaluation */

static int ns_push(xp_nodeset *ns, struct th_node *node, Py_ssize_t attr) {
    if (ns->len == ns->cap) {
        Py_ssize_t cap = ns->cap ? ns->cap * 2 : 8;
        xp_item *grown = PyMem_Realloc(ns->items, (size_t)cap * sizeof(xp_item));
        if (grown == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
            return -1;       /* GCOVR_EXCL_LINE */
        }
        ns->items = grown;
        ns->cap = cap;
    }
    ns->items[ns->len].node = node;
    ns->items[ns->len].attr = attr;
    ns->len++;
    return 0;
}

void xp_nodeset_free(xp_nodeset *ns) {
    PyMem_Free(ns->items);
    ns->items = NULL;
    ns->len = ns->cap = 0;
}

/* Resolve a name test to a static tag atom, or TH_TAG_UNKNOWN for a name no known
   HTML tag carries (non-ASCII, mixed case, or simply unknown); such a name then
   matches only unknown-atom elements with that exact spelling. */
static uint16_t resolve_tag_atom(const Py_UCS4 *name, Py_ssize_t len) {
    char buf[64];
    if (len >= (Py_ssize_t)sizeof(buf)) { /* a name this long is no known tag; the parser never makes an empty one */
        return TH_TAG_UNKNOWN;
    }
    for (Py_ssize_t index = 0; index < len; index++) {
        if (name[index] >= 0x80) {
            return TH_TAG_UNKNOWN;
        }
        buf[index] = (char)name[index];
    }
    return th_tag_lookup(buf, len);
}

static uint32_t resolve_attr_atom(struct th_tree *tree, const Py_UCS4 *name, Py_ssize_t len) {
    char buf[128];
    if (len >= (Py_ssize_t)sizeof(buf)) { /* no attribute name is this long; the parser never makes an empty one */
        return UINT32_MAX;
    }
    for (Py_ssize_t index = 0; index < len; index++) {
        if (name[index] >= 0x80) {
            return UINT32_MAX;
        }
        buf[index] = (char)name[index];
    }
    return th_attr_lookup(tree, buf, len);
}

static int element_name_matches(struct th_node *node, const xn *step, uint16_t atom) {
    if (atom != TH_TAG_UNKNOWN) {
        return node->atom == atom;
    }
    if (node->atom != TH_TAG_UNKNOWN || node->text_len != step->str_len) {
        return 0;
    }
    return memcmp(node->text, step->str, (size_t)step->str_len * sizeof(Py_UCS4)) == 0;
}

/* Whether a node satisfies a step's node test on an element-principal axis. */
static int node_test_matches(struct th_node *node, const xn *step, uint16_t atom) {
    switch (step->test) {
    case NT_NAME:
        return node->type == TH_NODE_ELEMENT && element_name_matches(node, step, atom);
    case NT_STAR:
        return node->type == TH_NODE_ELEMENT;
    case NT_TEXT:
        return node->type == TH_NODE_TEXT;
    case NT_COMMENT:
        return node->type == TH_NODE_COMMENT;
    case NT_PI:
        return node->type == TH_NODE_PI;
    default: /* NT_NODE */
        return 1;
    }
}

static struct th_node *descendant_next(struct th_node *node, struct th_node *root) {
    if (node->first_child != NULL) {
        return node->first_child;
    }
    while (node != root && node->next_sibling == NULL) {
        node = node->parent;
    }
    return node == root ? NULL : node->next_sibling;
}

/* Emit, into out, the nodes on ctx's `step` axis that pass the node test. */
/* Push node when it passes the step's node test. Returns 0, or -1 on allocation
   failure (which cannot be forced from a test). */
static int emit_if_match(xp_nodeset *out, struct th_node *node, const xn *step, uint16_t atom) {
    if (!node_test_matches(node, step, atom)) {
        return 0;
    }
    return ns_push(out, node, -1);
}

static int apply_step(xp_nodeset *out, struct th_node *ctx, const xn *step, uint16_t atom, uint32_t attr_atom) {
    switch (step->axis) {
    case AX_ATTRIBUTE:
        /* node() and * both match every attribute; a name test matches by atom;
           text()/comment()/processing-instruction() match no attribute. */
        for (Py_ssize_t index = 0; index < ctx->attr_count; index++) {
            int hit = step->test == NT_STAR || step->test == NT_NODE ||
                      (step->test == NT_NAME && ctx->attrs[index].name_atom == attr_atom);
            if (hit && ns_push(out, ctx, index) < 0) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
                return -1;                             /* GCOVR_EXCL_LINE */
            }
        }
        return 0;
    case AX_SELF:
        return emit_if_match(out, ctx, step, atom);
    case AX_CHILD:
        for (struct th_node *child = ctx->first_child; child != NULL; child = child->next_sibling) {
            if (emit_if_match(out, child, step, atom) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                return -1;                                   /* GCOVR_EXCL_LINE */
            }
        }
        return 0;
    case AX_DESCENDANT_OR_SELF:
        if (emit_if_match(out, ctx, step, atom) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            return -1;                                 /* GCOVR_EXCL_LINE */
        }
        /* FALLTHROUGH: descendant-or-self is self plus the descendant walk */
    case AX_DESCENDANT:
        for (struct th_node *node = ctx->first_child; node != NULL; node = descendant_next(node, ctx)) {
            if (emit_if_match(out, node, step, atom) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                return -1;                                  /* GCOVR_EXCL_LINE */
            }
        }
        return 0;
    case AX_PARENT:
        return ctx->parent != NULL ? emit_if_match(out, ctx->parent, step, atom) : 0;
    case AX_ANCESTOR_OR_SELF:
        if (emit_if_match(out, ctx, step, atom) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            return -1;                                 /* GCOVR_EXCL_LINE */
        }
        /* FALLTHROUGH: ancestor-or-self is self plus the ancestor walk */
    case AX_ANCESTOR:
        for (struct th_node *node = ctx->parent; node != NULL; node = node->parent) {
            if (emit_if_match(out, node, step, atom) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                return -1;                                  /* GCOVR_EXCL_LINE */
            }
        }
        return 0;
    case AX_FOLLOWING_SIBLING:
        for (struct th_node *node = ctx->next_sibling; node != NULL; node = node->next_sibling) {
            if (emit_if_match(out, node, step, atom) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                return -1;                                  /* GCOVR_EXCL_LINE */
            }
        }
        return 0;
    default: /* AX_PRECEDING_SIBLING */
        for (struct th_node *node = ctx->prev_sibling; node != NULL; node = node->prev_sibling) {
            if (emit_if_match(out, node, step, atom) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                return -1;                                  /* GCOVR_EXCL_LINE */
            }
        }
        return 0;
    }
}

static Py_ssize_t node_depth(struct th_node *node) {
    Py_ssize_t depth = 0;
    while (node->parent != NULL) {
        node = node->parent;
        depth++;
    }
    return depth;
}

/* Negative when x precedes y in document (pre-order); positive otherwise. Never
   called with x == y. */
static int node_before(struct th_node *left, struct th_node *right) {
    Py_ssize_t dx = node_depth(left);
    Py_ssize_t dy = node_depth(right);
    struct th_node *walk_left = left;
    struct th_node *walk_right = right;
    for (Py_ssize_t index = dx; index > dy; index--) {
        walk_left = walk_left->parent;
    }
    for (Py_ssize_t index = dy; index > dx; index--) {
        walk_right = walk_right->parent;
    }
    if (walk_left == walk_right) {
        return dx < dy ? -1 : 1; /* the shallower original node is an ancestor of the other */
    }
    while (walk_left->parent != walk_right->parent) {
        walk_left = walk_left->parent;
        walk_right = walk_right->parent;
    }
    for (struct th_node *sibling = walk_left->next_sibling; sibling != NULL; sibling = sibling->next_sibling) {
        if (sibling == walk_right) {
            return -1;
        }
    }
    return 1;
}

static int item_cmp(const void *pa, const void *pb) {
    const xp_item *left = pa;
    const xp_item *right = pb;
    if (left->node == right->node) {
        return left->attr < right->attr ? -1 : 1; /* same node: the node (-1) sorts before its attributes */
    }
    return node_before(left->node, right->node);
}

static void sort_unique(xp_nodeset *ns) {
    if (ns->len < 2) {
        return;
    }
    qsort(ns->items, (size_t)ns->len, sizeof(xp_item), item_cmp);
    Py_ssize_t write_pos = 1;
    for (Py_ssize_t read_pos = 1; read_pos < ns->len; read_pos++) {
        if (ns->items[read_pos].node != ns->items[write_pos - 1].node ||
            ns->items[read_pos].attr != ns->items[write_pos - 1].attr) {
            ns->items[write_pos++] = ns->items[read_pos];
        }
    }
    ns->len = write_pos;
}

static int axis_supported(uint8_t axis) {
    return axis != AX_FOLLOWING && axis != AX_PRECEDING && axis != AX_NAMESPACE;
}

/* --------------------------------------------------------- value model */

/* The evaluation context: the tree, the current node, its 1-based proximity
   position and the context size, plus where to report an unimplemented feature. */
typedef struct {
    struct th_tree *tree;
    struct th_node *node;
    Py_ssize_t pos;
    Py_ssize_t size;
    const char **feature;
} xp_ctx;

void xp_result_free(xp_result *result) {
    if (result->kind == XP_STRING) {
        PyMem_Free(result->string);
        result->string = NULL;
    } else if (result->kind == XP_NODESET) {
        xp_nodeset_free(&result->nodes);
    }
}

static void result_bool(xp_result *result, int value) {
    memset(result, 0, sizeof(*result));
    result->kind = XP_BOOLEAN;
    result->boolean = value != 0;
}

static void result_number(xp_result *result, double value) {
    memset(result, 0, sizeof(*result));
    result->kind = XP_NUMBER;
    result->number = value;
}

static void result_string(xp_result *result, Py_UCS4 *owned, Py_ssize_t len) {
    memset(result, 0, sizeof(*result));
    result->kind = XP_STRING;
    result->string = owned;
    result->string_len = len;
}

static Py_UCS4 *ucs4_dup(const Py_UCS4 *src, Py_ssize_t len) {
    Py_UCS4 *buf = PyMem_Malloc((size_t)len * sizeof(Py_UCS4));
    if (buf == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        return NULL;   /* GCOVR_EXCL_LINE */
    }
    if (len) {
        memcpy(buf, src, (size_t)len * sizeof(Py_UCS4));
    }
    return buf;
}

/* The XPath string-value of a node-set member, freshly allocated. */
static Py_UCS4 *item_string(struct th_tree *tree, xp_item item, Py_ssize_t *len) {
    if (item.attr >= 0) {
        const th_node_attr *attr_record = &item.node->attrs[item.attr];
        *len = attr_record->value == NULL ? 0 : attr_record->value_len;
        return ucs4_dup(attr_record->value, *len);
    }
    if (item.node->type == TH_NODE_TEXT || item.node->type == TH_NODE_COMMENT) {
        return th_node_data(tree, item.node, len);
    }
    return th_node_text(tree, item.node, len);
}

/* XPath number parse: optional leading/trailing whitespace around an optional sign,
   digits, and attr_record fractional part; anything else is NaN. */
static double parse_number(const Py_UCS4 *text, Py_ssize_t len) {
    Py_ssize_t index = 0;
    while (index < len && xp_is_space(text[index])) {
        index++;
    }
    Py_ssize_t end = len;
    while (end > index && xp_is_space(text[end - 1])) {
        end--;
    }
    if (index == end) {
        return (double)NAN;
    }
    int sign = 1;
    if (text[index] == '-') {
        sign = -1;
        index++;
    }
    double value = 0;
    double frac = 0;
    double scale = 1;
    int seen_digit = 0;
    int after_dot = 0;
    for (; index < end; index++) {
        Py_UCS4 ch = text[index];
        if (ch == '.' && !after_dot) {
            after_dot = 1;
        } else if (ch >= '0' && ch <= '9') {
            seen_digit = 1;
            if (after_dot) {
                scale *= 10;
                frac += (ch - '0') / scale;
            } else {
                value = value * 10 + (ch - '0');
            }
        } else {
            return (double)NAN;
        }
    }
    return seen_digit ? sign * (value + frac) : (double)NAN;
}

static int format_number(double value, Py_UCS4 **out, Py_ssize_t *out_len) {
    char buf[64];
    if (isnan(value)) {
        memcpy(buf, "NaN", 4);
    } else if (isinf(value)) {
        memcpy(buf, value < 0 ? "-Infinity" : "Infinity", value < 0 ? 10 : 9);
    } else if (value == (double)(long long)value && fabs(value) < 1e15) {
        snprintf(buf, sizeof(buf), "%lld", (long long)value);
    } else {
        snprintf(buf, sizeof(buf), "%.12g", value);
    }
    Py_ssize_t len = (Py_ssize_t)strlen(buf);
    Py_UCS4 *buffer = PyMem_Malloc((size_t)len * sizeof(Py_UCS4));
    if (buffer == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        return -1;        /* GCOVR_EXCL_LINE */
    }
    for (Py_ssize_t index = 0; index < len; index++) {
        buffer[index] = (Py_UCS4)(unsigned char)buf[index];
    }
    *out = buffer;
    *out_len = len;
    return 0;
}

static int to_boolean(struct th_tree *tree, const xp_result *value) {
    switch (value->kind) {
    case XP_BOOLEAN:
        return value->boolean;
    case XP_NUMBER:
        return value->number != 0 && !isnan(value->number);
    case XP_STRING:
        return value->string_len > 0;
    default: /* XP_NODESET */
        (void)tree;
        return value->nodes.len > 0;
    }
}

/* The string-value of value, freshly allocated; *len receives the length. */
static Py_UCS4 *to_string(struct th_tree *tree, const xp_result *value, Py_ssize_t *len) {
    switch (value->kind) {
    case XP_STRING:
        *len = value->string_len;
        return ucs4_dup(value->string, value->string_len);
    case XP_BOOLEAN: {
        const char *literal = value->boolean ? "true" : "false";
        *len = (Py_ssize_t)strlen(literal);
        Py_UCS4 *buffer = PyMem_Malloc((size_t)*len * sizeof(Py_UCS4));
        if (buffer == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
            return NULL;      /* GCOVR_EXCL_LINE */
        }
        for (Py_ssize_t index = 0; index < *len; index++) {
            buffer[index] = (Py_UCS4)(unsigned char)literal[index];
        }
        return buffer;
    }
    case XP_NUMBER: {
        Py_UCS4 *buffer = NULL;
        if (format_number(value->number, &buffer, len) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            return NULL;                                      /* GCOVR_EXCL_LINE */
        }
        return buffer;
    }
    default: /* XP_NODESET: string-value of the first node in document order */
        if (value->nodes.len == 0) {
            *len = 0;
            return ucs4_dup(NULL, 0);
        }
        return item_string(tree, value->nodes.items[0], len);
    }
}

static double to_number(struct th_tree *tree, const xp_result *value) {
    if (value->kind == XP_NUMBER) {
        return value->number;
    }
    if (value->kind == XP_BOOLEAN) {
        return value->boolean ? 1.0 : 0.0;
    }
    Py_ssize_t len;
    Py_UCS4 *text = to_string(tree, value, &len);
    if (text == NULL) {     /* GCOVR_EXCL_BR_LINE: alloc */
        return (double)NAN; /* GCOVR_EXCL_LINE */
    }
    double number = parse_number(text, len);
    PyMem_Free(text);
    return number;
}

/* ---------------------------------------------------------- evaluation */

static int eval_expr(const xp_program *prog, int32_t idx, xp_ctx *ctx, xp_result *out);

/* Apply each predicate in the XN_PRED chain to set, in place, in proximity order. */
static int apply_predicates(const xp_program *prog, int32_t pred_head, xp_ctx *ctx, xp_nodeset *set) {
    for (int32_t pr = pred_head; pr >= 0; pr = prog->nodes[pr].next) {
        int32_t expr = prog->nodes[pr].first;
        Py_ssize_t size = set->len;
        Py_ssize_t write_pos = 0;
        for (Py_ssize_t index = 0; index < set->len; index++) {
            xp_ctx pctx = {ctx->tree, set->items[index].node, index + 1, size, ctx->feature};
            xp_result value;
            int rc = eval_expr(prog, expr, &pctx, &value);
            if (rc < 0) {
                return rc;
            }
            int keep = value.kind == XP_NUMBER ? (double)(index + 1) == value.number : to_boolean(ctx->tree, &value);
            xp_result_free(&value);
            if (keep) {
                set->items[write_pos++] = set->items[index];
            }
        }
        set->len = write_pos;
    }
    return 0;
}

/* Evaluate an XN_PATH (optionally with a filter base) into a node-set. */
static int eval_path(const xp_program *prog, int32_t path_idx, xp_ctx *ctx, xp_nodeset *out) {
    const xn *root = &prog->nodes[path_idx];
    xp_nodeset cur = {0};
    if (root->second >= 0) {
        xp_result base;
        int rc = eval_expr(prog, root->second, ctx, &base);
        if (rc < 0) {
            return rc;
        }
        if (base.kind != XP_NODESET) {
            xp_result_free(&base);
            *ctx->feature = "a path step on a non-node-set";
            return -2;
        }
        cur = base.nodes; /* take ownership */
    } else {
        struct th_node *start = root->absolute ? th_tree_document(ctx->tree) : ctx->node;
        if (ns_push(&cur, start, -1) < 0) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
            return -1;                      /* GCOVR_EXCL_LINE */
        }
    }
    xp_nodeset next = {0};
    for (int32_t si = root->first; si >= 0; si = prog->nodes[si].next) {
        const xn *step = &prog->nodes[si];
        if (!axis_supported(step->axis)) {
            *ctx->feature = "the following/preceding/namespace axes";
            xp_nodeset_free(&cur);
            xp_nodeset_free(&next);
            return -2;
        }
        int name_test = step->test == NT_NAME;
        uint16_t atom = name_test && step->axis != AX_ATTRIBUTE ? resolve_tag_atom(step->str, step->str_len) : 0;
        uint32_t attr_atom = name_test && step->axis == AX_ATTRIBUTE
                                 ? resolve_attr_atom(ctx->tree, step->str, step->str_len)
                                 : UINT32_MAX;
        next.len = 0;
        for (Py_ssize_t index = 0; index < cur.len; index++) {
            if (cur.items[index].attr >= 0) {
                continue; /* an attribute has no axes of its own */
            }
            Py_ssize_t before = next.len;
            if (apply_step(&next, cur.items[index].node, step, atom, attr_atom) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                xp_nodeset_free(&cur);                                                 /* GCOVR_EXCL_LINE */
                xp_nodeset_free(&next);                                                /* GCOVR_EXCL_LINE */
                return -1;                                                             /* GCOVR_EXCL_LINE */
            }
            if (step->first >= 0) {
                /* filter this context node's candidates in proximity order */
                xp_nodeset slice = {next.items + before, next.len - before, 0};
                int rc = apply_predicates(prog, step->first, ctx, &slice);
                if (rc < 0) {
                    xp_nodeset_free(&cur);
                    xp_nodeset_free(&next);
                    return rc;
                }
                next.len = before + slice.len;
            }
        }
        xp_nodeset swap = cur;
        cur = next;
        next = swap;
        sort_unique(&cur);
    }
    xp_nodeset_free(&next);
    *out = cur;
    return 0;
}

/* Existential comparison of two scalar values (neither a node-set). */
static int cmp_scalar(struct th_tree *tree, int op, const xp_result *left, const xp_result *right) {
    if (op == XN_EQ || op == XN_NE) {
        int eq;
        if (left->kind == XP_BOOLEAN || right->kind == XP_BOOLEAN) {
            eq = to_boolean(tree, left) == to_boolean(tree, right);
        } else if (left->kind == XP_NUMBER || right->kind == XP_NUMBER) {
            eq = to_number(tree, left) == to_number(tree, right);
        } else {
            Py_ssize_t la;
            Py_ssize_t lb;
            Py_UCS4 *sa = to_string(tree, left, &la);
            Py_UCS4 *sb = to_string(tree, right, &lb);
            if (sa == NULL || sb == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
                eq = 0;                     /* GCOVR_EXCL_LINE */
            } else {
                eq = la == lb && memcmp(sa, sb, (size_t)la * sizeof(Py_UCS4)) == 0;
            }
            PyMem_Free(sa);
            PyMem_Free(sb);
        }
        return op == XN_EQ ? eq : !eq;
    }
    double left_num = to_number(tree, left);
    double right_num = to_number(tree, right);
    switch (op) {
    case XN_LT:
        return left_num < right_num;
    case XN_LE:
        return left_num <= right_num;
    case XN_GT:
        return left_num > right_num;
    default: /* XN_GE */
        return left_num >= right_num;
    }
}

/* A node-set member wrapped as left standalone string value. */
static int item_as_string(struct th_tree *tree, xp_item item, xp_result *out) {
    Py_ssize_t len;
    Py_UCS4 *text = item_string(tree, item, &len);
    if (text == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        return -1;      /* GCOVR_EXCL_LINE */
    }
    result_string(out, text, len);
    return 0;
}

static int compare(struct th_tree *tree, int op, xp_result *first, xp_result *second, int *result) {
    int a_ns = first->kind == XP_NODESET;
    int b_ns = second->kind == XP_NODESET;
    if (!a_ns && !b_ns) {
        *result = cmp_scalar(tree, op, first, second);
        return 0;
    }
    /* first node-set compared with first boolean uses the node-set's own boolean value */
    if ((a_ns && second->kind == XP_BOOLEAN) || (b_ns && first->kind == XP_BOOLEAN)) {
        *result = cmp_scalar(tree, op, first, second);
        return 0;
    }
    xp_nodeset *left = a_ns ? &first->nodes : NULL;
    xp_nodeset *right = b_ns ? &second->nodes : NULL;
    *result = 0;
    if (a_ns && b_ns) {
        for (Py_ssize_t index = 0; index < left->len && !*result; index++) {
            xp_result si;
            if (item_as_string(tree, left->items[index], &si) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                return -1;                                           /* GCOVR_EXCL_LINE */
            }
            for (Py_ssize_t inner_index = 0; inner_index < right->len && !*result; inner_index++) {
                xp_result sj;
                if (item_as_string(tree, right->items[inner_index], &sj) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                    xp_result_free(&si);                                        /* GCOVR_EXCL_LINE */
                    return -1;                                                  /* GCOVR_EXCL_LINE */
                }
                *result = cmp_scalar(tree, op, &si, &sj);
                xp_result_free(&sj);
            }
            xp_result_free(&si);
        }
        return 0;
    }
    xp_nodeset *ns = a_ns ? left : right;
    xp_result *other = a_ns ? second : first;
    for (Py_ssize_t index = 0; index < ns->len && !*result; index++) {
        xp_result si;
        if (item_as_string(tree, ns->items[index], &si) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            return -1;                                         /* GCOVR_EXCL_LINE */
        }
        *result = a_ns ? cmp_scalar(tree, op, &si, other) : cmp_scalar(tree, op, other, &si);
        xp_result_free(&si);
    }
    return 0;
}

/* -------------------------------------------------------- function library */

/* number() with no argument: the context node's string-value parsed as first number. */
static double context_node_number(xp_ctx *ctx) {
    xp_item item = {ctx->node, -1};
    Py_ssize_t length;
    Py_UCS4 *text = item_string(ctx->tree, item, &length);
    if (text == NULL) {     /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced */
        return (double)NAN; /* GCOVR_EXCL_LINE */
    }
    double value = parse_number(text, length);
    PyMem_Free(text);
    return value;
}

static int func_is(const xn *fn, const char *kw) {
    Py_ssize_t index = 0;
    for (; kw[index] != '\0'; index++) {
        if (index >= fn->str_len || fn->str[index] != (Py_UCS4)(unsigned char)kw[index]) {
            return 0;
        }
    }
    return index == fn->str_len;
}

static Py_ssize_t ucs4_find(const Py_UCS4 *hay, Py_ssize_t hlen, const Py_UCS4 *needle, Py_ssize_t nlen) {
    if (nlen == 0) {
        return 0;
    }
    for (Py_ssize_t index = 0; index + nlen <= hlen; index++) {
        if (memcmp(hay + index, needle, (size_t)nlen * sizeof(Py_UCS4)) == 0) {
            return index;
        }
    }
    return -1;
}

/* The string-value to operate on: the first argument's, or the context node's when
   the function was called with no arguments. */
static Py_UCS4 *arg_or_context_string(xp_ctx *ctx, xp_result *args, int argc, Py_ssize_t *len) {
    if (argc >= 1) {
        return to_string(ctx->tree, &args[0], len);
    }
    xp_item item = {ctx->node, -1};
    return item_string(ctx->tree, item, len);
}

/* The qualified name of a node-set's first node (or the context node), as a fresh
   string; empty for a non-named node or an empty node-set. */
static Py_UCS4 *node_name_string(xp_ctx *ctx, xp_result *args, int argc, Py_ssize_t *len) {
    struct th_node *node = ctx->node;
    Py_ssize_t attr = -1;
    if (argc >= 1) {
        if (args[0].kind != XP_NODESET || args[0].nodes.len == 0) {
            *len = 0;
            return ucs4_dup(NULL, 0);
        }
        node = args[0].nodes.items[0].node;
        attr = args[0].nodes.items[0].attr;
    }
    if (attr >= 0) {
        Py_ssize_t blen;
        const char *bytes = th_attr_name(ctx->tree, node->attrs[attr].name_atom, &blen);
        Py_UCS4 *buffer =
            PyMem_Malloc((size_t)blen * sizeof(Py_UCS4)); /* GCOVR_EXCL_BR_LINE: attribute names are never empty */
        if (buffer == NULL) {                             /* GCOVR_EXCL_BR_LINE: alloc */
            return NULL;                                  /* GCOVR_EXCL_LINE */
        }
        for (Py_ssize_t index = 0; index < blen; index++) {
            buffer[index] = (Py_UCS4)(unsigned char)bytes[index];
        }
        *len = blen;
        return buffer;
    }
    if (node->type == TH_NODE_ELEMENT) {
        *len = node->text_len;
        return ucs4_dup(node->text, node->text_len);
    }
    *len = 0;
    return ucs4_dup(NULL, 0);
}

/* normalize-space: trim ends, collapse internal whitespace runs to one space. */
static int normalize_space(const Py_UCS4 *text, Py_ssize_t len, xp_result *out) {
    Py_UCS4 *buf = PyMem_Malloc((size_t)len * sizeof(Py_UCS4));
    if (buf == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        return -1;     /* GCOVR_EXCL_LINE */
    }
    Py_ssize_t write_pos = 0;
    int in_space = 1; /* leading whitespace is dropped */
    for (Py_ssize_t index = 0; index < len; index++) {
        if (xp_is_space(text[index])) {
            in_space = 1;
        } else {
            if (in_space && write_pos > 0) {
                buf[write_pos++] = ' ';
            }
            buf[write_pos++] = text[index];
            in_space = 0;
        }
    }
    result_string(out, buf, write_pos);
    return 0;
}

static int translate(const Py_UCS4 *text, Py_ssize_t slen, const Py_UCS4 *from, Py_ssize_t flen, const Py_UCS4 *to,
                     Py_ssize_t tlen, xp_result *out) {
    Py_UCS4 *buf = PyMem_Malloc((size_t)slen * sizeof(Py_UCS4));
    if (buf == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        return -1;     /* GCOVR_EXCL_LINE */
    }
    Py_ssize_t write_pos = 0;
    for (Py_ssize_t index = 0; index < slen; index++) {
        Py_ssize_t from_index = 0;
        while (from_index < flen && from[from_index] != text[index]) {
            from_index++;
        }
        if (from_index >= flen) {
            buf[write_pos++] = text[index];
        } else if (from_index < tlen) {
            buf[write_pos++] = to[from_index];
        }
        /* else: in `from` but past the end of `to`, so the character is removed */
    }
    result_string(out, buf, write_pos);
    return 0;
}

static int substring(struct th_tree *tree, xp_result *args, int argc, xp_result *out) {
    Py_ssize_t slen;
    Py_UCS4 *text = to_string(tree, &args[0], &slen);
    if (text == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        return -1;      /* GCOVR_EXCL_LINE */
    }
    double start = round(to_number(tree, &args[1]));
    double last = argc >= 3 ? start + round(to_number(tree, &args[2])) : (double)slen + 1;
    Py_ssize_t lo = start < 1 ? 0 : (start > (double)slen + 1 ? slen : (Py_ssize_t)start - 1);
    Py_ssize_t hi = last < 1 ? 0 : (last > (double)slen + 1 ? slen : (Py_ssize_t)last - 1);
    if (hi < lo) {
        hi = lo;
    }
    Py_UCS4 *result_text = ucs4_dup(text + lo, hi - lo);
    PyMem_Free(text);
    if (result_text == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        return -1;             /* GCOVR_EXCL_LINE */
    }
    result_string(out, result_text, hi - lo);
    return 0;
}

static int eval_function(const xp_program *prog, int32_t idx, xp_ctx *ctx, xp_result *out) {
    const xn *fn = &prog->nodes[idx];
    xp_result args[8];
    int argc = 0;
    for (int32_t arg_node = fn->first; arg_node >= 0; arg_node = prog->nodes[arg_node].next) {
        if (argc == 8) { /* GCOVR_EXCL_BR_LINE: no supported function takes 8 args */
            *ctx->feature = "a function with too many arguments";                /* GCOVR_EXCL_LINE */
            for (int cleanup_index = 0; cleanup_index < argc; cleanup_index++) { /* GCOVR_EXCL_LINE */
                xp_result_free(&args[cleanup_index]);                            /* GCOVR_EXCL_LINE */
            } /* GCOVR_EXCL_LINE */
            return -2; /* GCOVR_EXCL_LINE */
        }
        int rc = eval_expr(prog, arg_node, ctx, &args[argc]);
        if (rc < 0) {
            for (int cleanup_index = 0; cleanup_index < argc; cleanup_index++) {
                xp_result_free(&args[cleanup_index]);
            }
            return rc;
        }
        argc++;
    }
    int rc = 0;
    if (func_is(fn, "true") || func_is(fn, "false")) {
        result_bool(out, func_is(fn, "true"));
    } else if (func_is(fn, "position")) {
        result_number(out, (double)ctx->pos);
    } else if (func_is(fn, "last")) {
        result_number(out, (double)ctx->size);
    } else if (func_is(fn, "not")) {
        result_bool(out, !to_boolean(ctx->tree, &args[0]));
    } else if (func_is(fn, "boolean")) {
        result_bool(out, to_boolean(ctx->tree, &args[0]));
    } else if (func_is(fn, "number")) {
        result_number(out, argc >= 1 ? to_number(ctx->tree, &args[0]) : context_node_number(ctx));
    } else if (func_is(fn, "floor") || func_is(fn, "ceiling") || func_is(fn, "round")) {
        double value = to_number(ctx->tree, &args[0]);
        result_number(out, func_is(fn, "floor") ? floor(value) : func_is(fn, "ceiling") ? ceil(value) : round(value));
    } else if (func_is(fn, "count")) {
        if (args[0].kind != XP_NODESET) {
            *ctx->feature = "count() of a non-node-set";
            rc = -2;
        } else {
            result_number(out, (double)args[0].nodes.len);
        }
    } else if (func_is(fn, "sum")) {
        if (args[0].kind != XP_NODESET) {
            *ctx->feature = "sum() of a non-node-set";
            rc = -2;
        } else {
            double total = 0;
            for (Py_ssize_t index = 0; index < args[0].nodes.len; index++) {
                Py_ssize_t length;
                Py_UCS4 *text = item_string(ctx->tree, args[0].nodes.items[index], &length);
                if (text == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
                    rc = -1;        /* GCOVR_EXCL_LINE */
                    break;          /* GCOVR_EXCL_LINE */
                }
                total += parse_number(text, length);
                PyMem_Free(text);
            }
            if (rc == 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                result_number(out, total);
            }
        }
    } else if (func_is(fn, "string")) {
        Py_ssize_t length;
        Py_UCS4 *text = arg_or_context_string(ctx, args, argc, &length);
        rc = text == NULL ? -1 : 0; /* GCOVR_EXCL_BR_LINE: alloc */
        if (rc == 0) {              /* GCOVR_EXCL_BR_LINE: alloc */
            result_string(out, text, length);
        }
    } else if (func_is(fn, "string-length")) {
        Py_ssize_t length;
        Py_UCS4 *text = arg_or_context_string(ctx, args, argc, &length);
        rc = text == NULL ? -1 : 0; /* GCOVR_EXCL_BR_LINE: alloc */
        if (rc == 0) {              /* GCOVR_EXCL_BR_LINE: alloc */
            result_number(out, (double)length);
            PyMem_Free(text);
        }
    } else if (func_is(fn, "normalize-space")) {
        Py_ssize_t length;
        Py_UCS4 *text = arg_or_context_string(ctx, args, argc, &length);
        rc = text == NULL ? -1 : normalize_space(text, length, out); /* GCOVR_EXCL_BR_LINE: alloc */
        PyMem_Free(text);
    } else if (func_is(fn, "local-name") || func_is(fn, "name")) {
        Py_ssize_t length;
        Py_UCS4 *text = node_name_string(ctx, args, argc, &length);
        rc = text == NULL ? -1 : 0; /* GCOVR_EXCL_BR_LINE: alloc */
        if (rc == 0) {              /* GCOVR_EXCL_BR_LINE: alloc */
            result_string(out, text, length);
        }
    } else if (func_is(fn, "concat")) {
        Py_ssize_t total = 0;
        Py_UCS4 *parts[8];
        Py_ssize_t lens[8];
        for (int index = 0; index < argc; index++) {
            parts[index] = to_string(ctx->tree, &args[index], &lens[index]);
            if (parts[index] == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
                rc = -1;                /* GCOVR_EXCL_LINE */
            } /* GCOVR_EXCL_LINE */
            total += lens[index];
        }
        if (rc == 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            Py_UCS4 *buf = PyMem_Malloc((size_t)total * sizeof(Py_UCS4));
            if (buf == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
                rc = -1;       /* GCOVR_EXCL_LINE */
            } else {
                Py_ssize_t write_pos = 0;
                for (int index = 0; index < argc; index++) {
                    memcpy(buf + write_pos, parts[index], (size_t)lens[index] * sizeof(Py_UCS4));
                    write_pos += lens[index];
                }
                result_string(out, buf, total);
            }
        }
        for (int index = 0; index < argc; index++) {
            PyMem_Free(parts[index]);
        }
    } else if (func_is(fn, "starts-with") || func_is(fn, "contains")) {
        Py_ssize_t hl;
        Py_ssize_t nl;
        Py_UCS4 *hay = to_string(ctx->tree, &args[0], &hl);
        Py_UCS4 *needle = to_string(ctx->tree, &args[1], &nl);
        if (hay == NULL || needle == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
            rc = -1;                         /* GCOVR_EXCL_LINE */
        } else if (func_is(fn, "starts-with")) {
            result_bool(out, nl <= hl && memcmp(hay, needle, (size_t)nl * sizeof(Py_UCS4)) == 0);
        } else {
            result_bool(out, ucs4_find(hay, hl, needle, nl) >= 0);
        }
        PyMem_Free(hay);
        PyMem_Free(needle);
    } else if (func_is(fn, "substring-before") || func_is(fn, "substring-after")) {
        Py_ssize_t hl;
        Py_ssize_t nl;
        Py_UCS4 *hay = to_string(ctx->tree, &args[0], &hl);
        Py_UCS4 *needle = to_string(ctx->tree, &args[1], &nl);
        if (hay == NULL || needle == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
            rc = -1;                         /* GCOVR_EXCL_LINE */
        } else {
            Py_ssize_t at = ucs4_find(hay, hl, needle, nl);
            const Py_UCS4 *start = at < 0 ? hay : func_is(fn, "substring-before") ? hay : hay + at + nl;
            Py_ssize_t rlen = at < 0 ? 0 : func_is(fn, "substring-before") ? at : hl - (at + nl);
            Py_UCS4 *result_text = ucs4_dup(start, rlen);
            rc = result_text == NULL ? -1 : 0; /* GCOVR_EXCL_BR_LINE: alloc */
            if (rc == 0) {                     /* GCOVR_EXCL_BR_LINE: alloc */
                result_string(out, result_text, rlen);
            }
        }
        PyMem_Free(hay);
        PyMem_Free(needle);
    } else if (func_is(fn, "substring")) {
        rc = substring(ctx->tree, args, argc, out);
    } else if (func_is(fn, "translate")) {
        Py_ssize_t sl;
        Py_ssize_t fl;
        Py_ssize_t tl;
        Py_UCS4 *text = to_string(ctx->tree, &args[0], &sl);
        Py_UCS4 *from = to_string(ctx->tree, &args[1], &fl);
        Py_UCS4 *to = to_string(ctx->tree, &args[2], &tl);
        if (text == NULL || from == NULL || to == NULL) { /* GCOVR_EXCL_BR_LINE: alloc cannot be forced */
            rc = -1;                                      /* GCOVR_EXCL_LINE */
        } else {
            rc = translate(text, sl, from, fl, to, tl, out);
        }
        PyMem_Free(text);
        PyMem_Free(from);
        PyMem_Free(to);
    } else {
        *ctx->feature = "this function";
        rc = -2;
    }
    for (int cleanup_index = 0; cleanup_index < argc; cleanup_index++) {
        xp_result_free(&args[cleanup_index]);
    }
    return rc;
}

/* Merge b'text items into arg_node (taking ownership of b'text storage on success). */
static int nodeset_union(xp_nodeset *target, xp_nodeset *source) {
    for (Py_ssize_t index = 0; index < source->len; index++) {
        if (ns_push(target, source->items[index].node, source->items[index].attr) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            return -1;                                                                   /* GCOVR_EXCL_LINE */
        }
    }
    xp_nodeset_free(source);
    sort_unique(target);
    return 0;
}

static int eval_expr(const xp_program *prog, int32_t idx, xp_ctx *ctx, xp_result *out) {
    const xn *expr = &prog->nodes[idx];
    switch (expr->kind) {
    case XN_NUM:
        result_number(out, expr->num);
        return 0;
    case XN_LIT: {
        Py_UCS4 *text = ucs4_dup(expr->str, expr->str_len);
        if (text == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
            return -1;      /* GCOVR_EXCL_LINE */
        }
        result_string(out, text, expr->str_len);
        return 0;
    }
    case XN_PATH: {
        xp_nodeset ns = {0};
        int rc = eval_path(prog, idx, ctx, &ns);
        if (rc < 0) {
            return rc;
        }
        memset(out, 0, sizeof(*out));
        out->kind = XP_NODESET;
        out->nodes = ns;
        return 0;
    }
    case XN_FILTER: {
        xp_result primary;
        int rc = eval_expr(prog, expr->first, ctx, &primary);
        if (rc < 0) {
            return rc;
        }
        if (primary.kind != XP_NODESET) {
            xp_result_free(&primary);
            *ctx->feature = "a predicate on a non-node-set";
            return -2;
        }
        sort_unique(&primary.nodes);
        rc = apply_predicates(prog, expr->second, ctx, &primary.nodes);
        if (rc < 0) {
            xp_result_free(&primary);
            return rc;
        }
        *out = primary;
        return 0;
    }
    case XN_UNION: {
        xp_result left;
        xp_result right;
        int rc = eval_expr(prog, expr->first, ctx, &left);
        if (rc < 0) {
            return rc;
        }
        rc = eval_expr(prog, expr->second, ctx, &right);
        if (rc < 0) {
            xp_result_free(&left);
            return rc;
        }
        if (left.kind != XP_NODESET || right.kind != XP_NODESET) {
            xp_result_free(&left);
            xp_result_free(&right);
            *ctx->feature = "a union of non-node-sets";
            return -2;
        }
        if (nodeset_union(&left.nodes, &right.nodes) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
            xp_result_free(&left);                          /* GCOVR_EXCL_LINE */
            return -1;                                      /* GCOVR_EXCL_LINE */
        }
        *out = left;
        return 0;
    }
    case XN_OR:
    case XN_AND: {
        xp_result left;
        int rc = eval_expr(prog, expr->first, ctx, &left);
        if (rc < 0) {
            return rc;
        }
        int la = to_boolean(ctx->tree, &left);
        xp_result_free(&left);
        if (expr->kind == XN_OR ? la : !la) {
            result_bool(out, expr->kind == XN_OR);
            return 0;
        }
        xp_result right;
        rc = eval_expr(prog, expr->second, ctx, &right);
        if (rc < 0) {
            return rc;
        }
        result_bool(out, to_boolean(ctx->tree, &right));
        xp_result_free(&right);
        return 0;
    }
    case XN_NEG: {
        xp_result left;
        int rc = eval_expr(prog, expr->first, ctx, &left);
        if (rc < 0) {
            return rc;
        }
        result_number(out, -to_number(ctx->tree, &left));
        xp_result_free(&left);
        return 0;
    }
    case XN_FUNC:
        return eval_function(prog, idx, ctx, out);
    default: { /* the comparison and arithmetic binary operators */
        xp_result left;
        xp_result right;
        int rc = eval_expr(prog, expr->first, ctx, &left);
        if (rc < 0) {
            return rc;
        }
        rc = eval_expr(prog, expr->second, ctx, &right);
        if (rc < 0) {
            xp_result_free(&left);
            return rc;
        }
        if (expr->kind <= XN_GE) { /* the default case holds only the comparison and arithmetic operators */
            int cmp = 0;
            rc = compare(ctx->tree, expr->kind, &left, &right, &cmp);
            if (rc == 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                result_bool(out, cmp);
            }
        } else {
            double left_value = to_number(ctx->tree, &left);
            double right_value = to_number(ctx->tree, &right);
            double value = expr->kind == XN_ADD   ? left_value + right_value
                           : expr->kind == XN_SUB ? left_value - right_value
                           : expr->kind == XN_MUL ? left_value * right_value
                           : expr->kind == XN_DIV ? left_value / right_value
                                                  : fmod(left_value, right_value);
            result_number(out, value);
        }
        xp_result_free(&left);
        xp_result_free(&right);
        return rc;
    }
    }
}

int xp_eval(const xp_program *prog, struct th_tree *tree, struct th_node *context, xp_result *out,
            const char **feature) {
    xp_ctx ctx = {tree, context, 1, 1, feature};
    return eval_expr(prog, prog->root, &ctx, out);
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
