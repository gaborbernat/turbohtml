/* A CSS selector engine over the node tree, #included into tree_type.c. A
   selector is compiled against the tree it will run on, so tag and attribute
   names resolve to interned atoms once and every match is an integer compare.
   Matching is right-to-left with backtracking on the descendant and general
   sibling combinators. This covers the common subset: type, universal, class,
   id, attribute operators, the four combinators, the :is()/:where()/:has()/:not()
   functional pseudo-classes, all grouped by commas. */

#ifndef TURBOHTML_SELECTOR_H
#define TURBOHTML_SELECTOR_H

#include "ascii.h"
#include "treebuilder.h"

enum sel_attr_op { OP_EXISTS, OP_EQ, OP_INCLUDE, OP_DASH, OP_PREFIX, OP_SUFFIX, OP_SUBSTR };

/* The functional pseudo-classes hold a nested selector list built from sel_complex,
   so the type is forward-declared here. */
typedef struct sel_complex sel_complex;

/* ':' pseudo-classes. The structural ones have fixed meaning (the nth-* variants
   carry An+B in nth_a/nth_b); the functional ones (:is/:where/:has/:not) carry a
   nested selector list in sub; the state ones read attributes/structure; :lang()
   and :dir() carry an argument (in name / nth_a); PSEUDO_NEVER is the live-UA-state
   set (:hover/:focus/...) that is valid but never matches a static tree. */
enum sel_pseudo {
    PSEUDO_NONE,
    PSEUDO_ROOT,
    PSEUDO_EMPTY,
    PSEUDO_FIRST_CHILD,
    PSEUDO_LAST_CHILD,
    PSEUDO_ONLY_CHILD,
    PSEUDO_FIRST_OF_TYPE,
    PSEUDO_LAST_OF_TYPE,
    PSEUDO_ONLY_OF_TYPE,
    PSEUDO_NTH_CHILD,
    PSEUDO_NTH_LAST_CHILD,
    PSEUDO_NTH_OF_TYPE,
    PSEUDO_NTH_LAST_OF_TYPE,
    PSEUDO_IS,
    PSEUDO_WHERE,
    PSEUDO_HAS,
    PSEUDO_NOT,
    PSEUDO_SCOPE,
    PSEUDO_CHECKED,
    PSEUDO_DISABLED,
    PSEUDO_ENABLED,
    PSEUDO_REQUIRED,
    PSEUDO_OPTIONAL,
    PSEUDO_READ_ONLY,
    PSEUDO_READ_WRITE,
    PSEUDO_DEFAULT,
    PSEUDO_LANG,
    PSEUDO_DIR,
    PSEUDO_NEVER,
};

typedef struct {
    char kind;          /* '*', 'e' type, '.' class, '#' id, '[' attribute, ':' pseudo-class */
    uint16_t tag_atom;  /* 'e': the tag atom, TH_TAG_UNKNOWN for a name outside the table */
    uint32_t attr_atom; /* '[': the attribute atom, UINT32_MAX when no element has the name */
    enum sel_attr_op op;
    int ci;               /* '[': matched case-insensitively (explicit i flag) */
    int ci_default;       /* '[': name is in the HTML case-insensitive set, no explicit s/i flag */
    int pseudo;           /* ':': the pseudo-class id (enum sel_pseudo) */
    int nth_a;            /* ':': the An+B "A" coefficient for an nth-* pseudo-class */
    int nth_b;            /* ':': the An+B "B" coefficient for an nth-* pseudo-class */
    const Py_UCS4 *name;  /* class / id / unknown tag name (into the owned source copy) */
    Py_ssize_t name_len;  /* also the attribute name for the rare unknown case */
    const Py_UCS4 *value; /* '[': the attribute value */
    Py_ssize_t value_len;
    sel_complex *sub; /* ':': the nested selector list for :is()/:where()/:has()/:not() */
    int sub_count;    /* ':': number of comma-separated alternatives in sub */
} sel_simple;

typedef struct {
    sel_simple *simples;
    int count;
    char combinator; /* ' ', '>', '+', '~': the combinator joining the compound on the left */
} sel_compound;

struct sel_complex {
    sel_compound *compounds; /* left to right; matched from the rightmost (the subject) */
    int count;
};

typedef struct {
    Py_UCS4 *source; /* an owned copy of the selector text the slices point into */
    sel_complex *alts;
    int count;
    int failed;    /* an allocation or a syntax error happened during compile */
    int quirks;    /* the tree was parsed in quirks mode: class/ID match case-insensitively */
    th_tree *tree; /* the tree this selector runs on; :empty reads text spans through it */
} sel_compiled;

/* ---------------------------------------------------------------- parsing */

typedef struct {
    Py_UCS4 *src; /* the owned source copy; sel_ident decodes escapes into it in place */
    Py_ssize_t pos;
    Py_ssize_t len;
    th_tree *tree;
    int error;
} sel_parser;

static int sel_is_ident(Py_UCS4 ch) {
    return is_ascii_alpha(ch) || (ch >= '0' && ch <= '9') || ch == '-' || ch == '_' || ch >= 0x80;
}

static int sel_is_hex(Py_UCS4 ch) {
    return (ch >= '0' && ch <= '9') || ((ch | 32) >= 'a' && (ch | 32) <= 'f');
}

static void sel_skip_ws(sel_parser *parser) {
    while (parser->pos < parser->len && is_space(parser->src[parser->pos])) {
        parser->pos++;
    }
}

/* Whether the backslash at parser->pos begins a valid escape: a backslash is
   one unless it precedes a CSS newline (LF/CR/FF); at end of input it still
   escapes the U+FFFD replacement character. */
static int sel_starts_escape(const sel_parser *parser) {
    if (parser->pos + 1 >= parser->len) {
        return 1;
    }
    Py_UCS4 next = parser->src[parser->pos + 1];
    return next != '\n' && next != '\r' && next != '\x0c';
}

/* Consume an escaped code point (CSS Syntax 4.3.7); the leading backslash at
   parser->pos is assumed to start a valid escape and is consumed here. */
static Py_UCS4 sel_consume_escape(sel_parser *parser) {
    parser->pos++; /* the backslash */
    if (parser->pos >= parser->len) {
        return 0xFFFD; /* a trailing backslash escapes the replacement character */
    }
    if (!sel_is_hex(parser->src[parser->pos])) {
        return parser->src[parser->pos++]; /* the literal escaped character */
    }
    uint32_t value = 0;
    for (int digit = 0; digit < 6 && parser->pos < parser->len && sel_is_hex(parser->src[parser->pos]); digit++) {
        Py_UCS4 hex = parser->src[parser->pos++];
        value = value * 16 + (hex <= '9' ? (uint32_t)(hex - '0') : (uint32_t)((hex | 32) - 'a' + 10));
    }
    if (parser->pos < parser->len && is_space(parser->src[parser->pos])) {
        parser->pos++; /* one trailing whitespace closes the hex escape */
    }
    if (value == 0 || value > 0x10FFFF || (value >= 0xD800 && value <= 0xDFFF)) {
        return 0xFFFD; /* null, surrogate, and out-of-range escapes fold to U+FFFD */
    }
    return (Py_UCS4)value;
}

/* Read an identifier run, decoding any CSS escapes in place (a decoded run is
   never longer than its source), and return its slice via *out / *out_len. */
static void sel_ident(sel_parser *parser, const Py_UCS4 **out, Py_ssize_t *out_len) {
    Py_ssize_t start = parser->pos;
    Py_ssize_t write = start;
    while (parser->pos < parser->len) {
        if (parser->src[parser->pos] == '\\') {
            if (!sel_starts_escape(parser)) {
                break; /* a backslash before a newline is not part of the identifier */
            }
            parser->src[write++] = sel_consume_escape(parser);
            continue;
        }
        if (!sel_is_ident(parser->src[parser->pos])) {
            break;
        }
        parser->src[write++] = parser->src[parser->pos++];
    }
    *out = parser->src + start;
    *out_len = write - start;
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

/* The HTML "case-sensitivity of selectors" attribute set: with no explicit s/i
   flag, an attribute selector on one of these names compares its value ASCII
   case-insensitively on HTML elements (WHATWG HTML, "Case-sensitivity of
   selectors"). Kept sorted for the binary search in sel_attr_default_ci. */
static const char *const SEL_CI_ATTRS[] = {
    "accept",   "accept-charset", "align",    "alink",      "axis",   "bgcolor",  "charset",   "checked",  "clear",
    "codetype", "color",          "compact",  "declare",    "defer",  "dir",      "direction", "disabled", "enctype",
    "face",     "frame",          "hreflang", "http-equiv", "lang",   "language", "link",      "media",    "method",
    "multiple", "nohref",         "noresize", "noshade",    "nowrap", "readonly", "rel",       "rev",      "rules",
    "scope",    "scrolling",      "selected", "shape",      "target", "text",     "type",      "valign",   "valuetype",
    "vlink",
};

/* Whether an attribute name (lowercased) is in the case-insensitive set. */
static int sel_attr_default_ci(const Py_UCS4 *name, Py_ssize_t len) {
    char buf[16]; /* the longest name, accept-charset, is 14 bytes */
    if (len >= (Py_ssize_t)sizeof(buf)) {
        return 0;
    }
    for (Py_ssize_t index = 0; index < len; index++) {
        Py_UCS4 ch = name[index];
        if (ch >= 'A' && ch <= 'Z') {
            ch += 32;
        }
        if (ch >= 0x80) {
            return 0; /* a non-ASCII name is never in the set */
        }
        buf[index] = (char)ch;
    }
    buf[len] = '\0';
    Py_ssize_t lo = 0;
    Py_ssize_t hi = (Py_ssize_t)(sizeof(SEL_CI_ATTRS) / sizeof(SEL_CI_ATTRS[0]));
    while (lo < hi) {
        Py_ssize_t mid = (lo + hi) / 2;
        int cmp = strcmp(buf, SEL_CI_ATTRS[mid]);
        if (cmp == 0) {
            return 1;
        }
        if (cmp < 0) {
            hi = mid;
        } else {
            lo = mid + 1;
        }
    }
    return 0;
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
    } else if (sel_attr_default_ci(name, name_len)) {
        simple->ci_default = 1; /* the HTML set defaults to case-insensitive without a flag */
    }
    if (parser->pos >= parser->len || parser->src[parser->pos] != ']') {
        parser->error = 1;
        return;
    }
    parser->pos++;
}

/* Parse the local part of a type selector (the part after an optional namespace
   prefix): '*' for the universal selector or an identifier for a tag name. */
static void sel_type_local(sel_parser *parser, sel_simple *simple) {
    if (parser->pos < parser->len && parser->src[parser->pos] == '*') {
        simple->kind = '*';
        parser->pos++;
    } else if (parser->pos < parser->len &&
               (sel_is_ident(parser->src[parser->pos]) || parser->src[parser->pos] == '\\')) {
        simple->kind = 'e';
        sel_ident(parser, &simple->name, &simple->name_len);
        simple->tag_atom = sel_tag_atom(simple->name, simple->name_len);
    } else {
        parser->error = 1; /* a namespace prefix must be followed by '*' or a type */
    }
}

/* Whether a name slice equals a lowercase ASCII keyword (ASCII case-insensitive). */
static int sel_kw(const Py_UCS4 *name, Py_ssize_t len, const char *kw) {
    if (len != (Py_ssize_t)strlen(kw)) {
        return 0;
    }
    for (Py_ssize_t index = 0; index < len; index++) {
        Py_UCS4 ch = name[index];
        if (ch >= 'A' && ch <= 'Z') {
            ch += 32;
        }
        if (ch != (Py_UCS4)(unsigned char)kw[index]) {
            return 0;
        }
    }
    return 1;
}

/* Read a run of ASCII digits as a non-negative int; *seen reports any digit. */
static int sel_read_int(sel_parser *parser, int *seen) {
    int value = 0;
    *seen = 0;
    while (parser->pos < parser->len && parser->src[parser->pos] >= '0' && parser->src[parser->pos] <= '9') {
        value = value * 10 + (int)(parser->src[parser->pos] - '0');
        parser->pos++;
        *seen = 1;
    }
    return value;
}

/* Parse the An+B microsyntax (CSS Syntax §"The An+B microsyntax") into a/b,
   including the even/odd keywords. pos starts after '(' and stops at the ')'. */
static void sel_parse_anb(sel_parser *parser, int *a, int *b) {
    sel_skip_ws(parser);
    if (parser->pos + 4 <= parser->len && sel_kw(parser->src + parser->pos, 4, "even")) {
        parser->pos += 4;
        *a = 2;
        *b = 0;
        sel_skip_ws(parser);
        return;
    }
    if (parser->pos + 3 <= parser->len && sel_kw(parser->src + parser->pos, 3, "odd")) {
        parser->pos += 3;
        *a = 2;
        *b = 1;
        sel_skip_ws(parser);
        return;
    }
    int sign = 1;
    if (parser->pos < parser->len && (parser->src[parser->pos] == '+' || parser->src[parser->pos] == '-')) {
        sign = parser->src[parser->pos] == '-' ? -1 : 1;
        parser->pos++;
    }
    int seen_a;
    int num = sel_read_int(parser, &seen_a);
    if (parser->pos < parser->len && (parser->src[parser->pos] | 32) == 'n') {
        parser->pos++;
        *a = sign * (seen_a ? num : 1);
        sel_skip_ws(parser);
        if (parser->pos < parser->len && (parser->src[parser->pos] == '+' || parser->src[parser->pos] == '-')) {
            int bsign = parser->src[parser->pos] == '-' ? -1 : 1;
            parser->pos++;
            sel_skip_ws(parser);
            int seen_b;
            int bval = sel_read_int(parser, &seen_b);
            if (!seen_b) {
                parser->error = 1;
                return;
            }
            *b = bsign * bval;
        } else {
            *b = 0;
        }
    } else if (seen_a) {
        *a = 0;
        *b = sign * num;
    } else {
        parser->error = 1; /* a bare sign with no digits and no 'n' is invalid */
        return;
    }
    sel_skip_ws(parser);
}

/* Parse the comma-separated selector list inside a :is()/:where()/:has(); defined
   below, after the complex-selector parser it drives. */
static int sel_parse_alts(sel_parser *parser, sel_complex **out_alts, int *out_count, int nested, int relative);
static void sel_free_alts(sel_complex *alts, int count);

/* The live UA/interaction-state pseudo-classes a static query engine cannot resolve:
   accepted as valid syntax but matched as a no-op (Selectors-4 §10/§11 dynamic set,
   plus :link/:any-link which need navigation state). */
static int sel_is_never_pseudo(const Py_UCS4 *name, Py_ssize_t len) {
    static const char *const NEVER[] = {"hover",  "focus",   "focus-within", "active",
                                        "target", "visited", "link",         "any-link"};
    for (size_t index = 0; index < sizeof(NEVER) / sizeof(NEVER[0]); index++) {
        if (sel_kw(name, len, NEVER[index])) {
            return 1;
        }
    }
    return 0;
}

/* Parse a pseudo-class selector (the leading ':' already consumed). */
static void sel_pseudo(sel_parser *parser, sel_simple *simple) {
    simple->kind = ':';
    const Py_UCS4 *name;
    Py_ssize_t name_len;
    sel_ident(parser, &name, &name_len);
    if (parser->error) {
        return;
    }
    int functional = PSEUDO_NONE; /* an nth-* pseudo-class taking An+B */
    int listy = PSEUDO_NONE;      /* :is()/:where()/:has()/:not() taking a selector list */
    int argy = PSEUDO_NONE;       /* :lang()/:dir() taking a single argument */
    if (sel_kw(name, name_len, "root")) {
        simple->pseudo = PSEUDO_ROOT;
    } else if (sel_kw(name, name_len, "empty")) {
        simple->pseudo = PSEUDO_EMPTY;
    } else if (sel_kw(name, name_len, "first-child")) {
        simple->pseudo = PSEUDO_FIRST_CHILD;
    } else if (sel_kw(name, name_len, "last-child")) {
        simple->pseudo = PSEUDO_LAST_CHILD;
    } else if (sel_kw(name, name_len, "only-child")) {
        simple->pseudo = PSEUDO_ONLY_CHILD;
    } else if (sel_kw(name, name_len, "first-of-type")) {
        simple->pseudo = PSEUDO_FIRST_OF_TYPE;
    } else if (sel_kw(name, name_len, "last-of-type")) {
        simple->pseudo = PSEUDO_LAST_OF_TYPE;
    } else if (sel_kw(name, name_len, "only-of-type")) {
        simple->pseudo = PSEUDO_ONLY_OF_TYPE;
    } else if (sel_kw(name, name_len, "nth-child")) {
        functional = PSEUDO_NTH_CHILD;
    } else if (sel_kw(name, name_len, "nth-last-child")) {
        functional = PSEUDO_NTH_LAST_CHILD;
    } else if (sel_kw(name, name_len, "nth-of-type")) {
        functional = PSEUDO_NTH_OF_TYPE;
    } else if (sel_kw(name, name_len, "nth-last-of-type")) {
        functional = PSEUDO_NTH_LAST_OF_TYPE;
    } else if (sel_kw(name, name_len, "is")) {
        listy = PSEUDO_IS;
    } else if (sel_kw(name, name_len, "where")) {
        listy = PSEUDO_WHERE;
    } else if (sel_kw(name, name_len, "has")) {
        listy = PSEUDO_HAS;
    } else if (sel_kw(name, name_len, "not")) {
        listy = PSEUDO_NOT;
    } else if (sel_kw(name, name_len, "scope")) {
        simple->pseudo = PSEUDO_SCOPE;
    } else if (sel_kw(name, name_len, "checked")) {
        simple->pseudo = PSEUDO_CHECKED;
    } else if (sel_kw(name, name_len, "disabled")) {
        simple->pseudo = PSEUDO_DISABLED;
    } else if (sel_kw(name, name_len, "enabled")) {
        simple->pseudo = PSEUDO_ENABLED;
    } else if (sel_kw(name, name_len, "required")) {
        simple->pseudo = PSEUDO_REQUIRED;
    } else if (sel_kw(name, name_len, "optional")) {
        simple->pseudo = PSEUDO_OPTIONAL;
    } else if (sel_kw(name, name_len, "read-only")) {
        simple->pseudo = PSEUDO_READ_ONLY;
    } else if (sel_kw(name, name_len, "read-write")) {
        simple->pseudo = PSEUDO_READ_WRITE;
    } else if (sel_kw(name, name_len, "default")) {
        simple->pseudo = PSEUDO_DEFAULT;
    } else if (sel_kw(name, name_len, "lang")) {
        argy = PSEUDO_LANG;
    } else if (sel_kw(name, name_len, "dir")) {
        argy = PSEUDO_DIR;
    } else if (sel_is_never_pseudo(name, name_len)) {
        /* live UA/interaction state (:hover/:focus/...): valid but never matches a
           static document, so it is accepted and resolves to a no-op rather than raising */
        simple->pseudo = PSEUDO_NEVER;
    } else {
        parser->error = 1; /* an unknown pseudo-class invalidates the selector */
        return;
    }
    if (functional != PSEUDO_NONE) {
        simple->pseudo = functional;
        if (parser->pos >= parser->len || parser->src[parser->pos] != '(') {
            parser->error = 1;
            return;
        }
        parser->pos++;
        sel_parse_anb(parser, &simple->nth_a, &simple->nth_b);
        if (parser->error) {
            return;
        }
        if (parser->pos >= parser->len || parser->src[parser->pos] != ')') {
            parser->error = 1;
            return;
        }
        parser->pos++;
    } else if (listy != PSEUDO_NONE) {
        simple->pseudo = listy;
        if (parser->pos >= parser->len || parser->src[parser->pos] != '(') {
            parser->error = 1; /* :is()/:where()/:has() require an argument list */
            return;
        }
        parser->pos++;
        sel_parse_alts(parser, &simple->sub, &simple->sub_count, 1, listy == PSEUDO_HAS);
    } else if (argy != PSEUDO_NONE) {
        simple->pseudo = argy;
        if (parser->pos >= parser->len || parser->src[parser->pos] != '(') {
            parser->error = 1; /* :lang()/:dir() require an argument */
            return;
        }
        parser->pos++;
        sel_skip_ws(parser);
        if (argy == PSEUDO_DIR) {
            const Py_UCS4 *arg;
            Py_ssize_t arg_len;
            sel_ident(parser, &arg, &arg_len); /* sets parser->error on an empty identifier */
            if (parser->error) {
                return;
            }
            /* a valid but unrecognized direction keeps :dir() valid yet never matching */
            simple->nth_a = sel_kw(arg, arg_len, "ltr") ? 1 : (sel_kw(arg, arg_len, "rtl") ? 2 : 0);
            sel_skip_ws(parser);
        } else { /* PSEUDO_LANG: keep the raw range list, tokenised on comma at match time */
            Py_ssize_t start = parser->pos;
            while (parser->pos < parser->len && parser->src[parser->pos] != ')') {
                parser->pos++;
            }
            Py_ssize_t end = parser->pos;
            while (end > start && is_space(parser->src[end - 1])) {
                end--;
            }
            if (end == start) {
                parser->error = 1; /* :lang() needs at least one range */
                return;
            }
            simple->name = parser->src + start;
            simple->name_len = end - start;
        }
        if (parser->pos >= parser->len || parser->src[parser->pos] != ')') {
            parser->error = 1;
            return;
        }
        parser->pos++;
    } else if (parser->pos < parser->len && parser->src[parser->pos] == '(') {
        parser->error = 1; /* a non-functional pseudo-class takes no argument list */
        return;
    }
}

/* Parse one simple selector into *simple. */
static void sel_one(sel_parser *parser, sel_simple *simple) {
    simple->tag_atom = TH_TAG_UNKNOWN;
    simple->attr_atom = 0;
    simple->ci = 0;
    simple->ci_default = 0;
    simple->pseudo = PSEUDO_NONE;
    simple->nth_a = 0;
    simple->nth_b = 0;
    simple->name = NULL;
    simple->name_len = 0;
    simple->value = NULL;
    simple->value_len = 0;
    simple->sub = NULL;
    simple->sub_count = 0;
    Py_UCS4 ch = parser->src[parser->pos];
    if (ch == '.' || ch == '#') {
        simple->kind = (char)ch;
        parser->pos++;
        sel_ident(parser, &simple->name, &simple->name_len);
    } else if (ch == ':') {
        parser->pos++;
        sel_pseudo(parser, simple);
    } else if (ch == '[') {
        parser->pos++;
        sel_attribute(parser, simple);
    } else if (ch == '|') {
        /* an empty (no-namespace) prefix; the prefix is ignored in a namespaceless
           HTML document, so |E reduces to E and |* to the universal selector */
        parser->pos++;
        sel_type_local(parser, simple);
    } else if (ch == '*' && parser->pos + 1 < parser->len && parser->src[parser->pos + 1] == '|') {
        /* a '*|' any-namespace prefix; ignored in HTML, so *|E reduces to E */
        parser->pos += 2;
        sel_type_local(parser, simple);
    } else if (ch == '*') {
        simple->kind = '*';
        parser->pos++;
    } else {
        /* an identifier: a tag name, or a namespace prefix when a '|' follows it.
           sel_starts_simple guarantees at least one char, so sel_ident succeeds */
        sel_ident(parser, &simple->name, &simple->name_len);
        if (parser->pos < parser->len && parser->src[parser->pos] == '|') {
            parser->pos++; /* an 'ns|' prefix; ignored in HTML, only the local part selects */
            simple->name = NULL;
            simple->name_len = 0;
            sel_type_local(parser, simple);
        } else {
            simple->kind = 'e';
            simple->tag_atom = sel_tag_atom(simple->name, simple->name_len);
        }
    }
}

static int sel_starts_simple(Py_UCS4 ch) {
    return ch == '*' || ch == '.' || ch == '#' || ch == '[' || ch == ':' || ch == '\\' || ch == '|' || sel_is_ident(ch);
}

/* Parse a compound (one or more adjacent simples) into the given buffer. */
static int sel_compound_parse(sel_parser *parser, sel_simple *buffer, int capacity) {
    int count = 0;
    while (parser->pos < parser->len && sel_starts_simple(parser->src[parser->pos])) {
        if (count >= capacity) {
            parser->error = 1;
            break;
        }
        sel_one(parser, &buffer[count]);
        if (parser->error) {
            break;
        }
        count++;
    }
    if (count == 0) {
        parser->error = 1;
    }
    if (parser->error) {
        /* free the nested lists of the pseudo-classes parsed before the failure; the
           simple that failed left its own sub NULL (sel_parse_alts cleans up on error) */
        for (int index = 0; index < count; index++) {
            if (buffer[index].sub != NULL) {
                sel_free_alts(buffer[index].sub, buffer[index].sub_count);
            }
        }
        return 0;
    }
    return count;
}

/* Parse one complex selector (compounds joined by combinators) into *complex,
   allocating its compounds. Returns 0, or -1 with parser->error set. */
static void sel_free_alts(sel_complex *alts, int count);

static void free_compounds(sel_compound *compounds, int count) {
    for (int index = 0; index < count; index++) {
        for (int simple = 0; simple < compounds[index].count; simple++) {
            if (compounds[index].simples[simple].sub != NULL) { /* a functional pseudo-class's nested list */
                sel_free_alts(compounds[index].simples[simple].sub, compounds[index].simples[simple].sub_count);
            }
        }
        PyMem_Free(compounds[index].simples);
    }
}

/* Free a comma-separated list of complex selectors and the array holding it (used
   for the top-level compiled selector and every nested :is()/:where()/:has() list). */
static void sel_free_alts(sel_complex *alts, int count) {
    for (int index = 0; index < count; index++) {
        free_compounds(alts[index].compounds, alts[index].count);
        PyMem_Free(alts[index].compounds);
    }
    PyMem_Free(alts);
}

static int sel_complex_parse(sel_parser *parser, sel_complex *complex, int nested, int relative) {
    sel_compound temp[32];
    int count = 0;
    char combinator = ' ';
    /* a relative selector (the argument of :has()) may open with a combinator, which
       joins its first compound to the anchor element instead of a left-hand compound */
    if (relative) {
        sel_skip_ws(parser);
        Py_UCS4 lead = parser->pos < parser->len ? parser->src[parser->pos] : 0;
        if (lead == '>' || lead == '+' || lead == '~') {
            combinator = (char)lead;
            parser->pos++;
            sel_skip_ws(parser);
        }
    }
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
        if (owned == NULL) {   /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
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
        if (ch == ',' || (nested && ch == ')')) {
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
        free_compounds(temp, count);
        return -1;
    }
    sel_compound *owned = PyMem_Malloc((size_t)count * sizeof(sel_compound));
    if (owned == NULL) {             /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        free_compounds(temp, count); /* GCOVR_EXCL_LINE: allocation-failure path */
        parser->error = 1;           /* GCOVR_EXCL_LINE: allocation-failure path */
        return -1;                   /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    memcpy(owned, temp, (size_t)count * sizeof(sel_compound));
    complex->compounds = owned;
    complex->count = count;
    return 0;
}

/* Parse a comma-separated list of complex selectors into a freshly allocated array.
   nested stops the list at a closing ')' (the :is()/:where()/:has() argument case)
   and requires that ')'; relative lets each complex open with a combinator (:has()).
   Returns 0 with the out parameters set, or -1 with parser->error set. */
static int sel_parse_alts(sel_parser *parser, sel_complex **out_alts, int *out_count, int nested, int relative) {
    sel_complex temp[64];
    int count = 0;
    while (1) {
        sel_skip_ws(parser);
        if (count >= 64) {
            parser->error = 1;
            break;
        }
        if (sel_complex_parse(parser, &temp[count], nested, relative) < 0) {
            break;
        }
        count++;
        sel_skip_ws(parser);
        if (parser->pos >= parser->len) {
            if (nested) {
                parser->error = 1; /* a ':is(...' that never closes its '(' */
            }
            break;
        }
        if (parser->src[parser->pos] == ',') {
            parser->pos++;
            continue;
        }
        /* a successful complex stops only at a comma, the end, or -- when nested -- the
           closing ')' that ends the argument list; consume it and finish */
        parser->pos++;
        break;
    }
    if (parser->error) {
        for (int index = 0; index < count; index++) {
            free_compounds(temp[index].compounds, temp[index].count);
            PyMem_Free(temp[index].compounds);
        }
        return -1;
    }
    sel_complex *owned = PyMem_Malloc((size_t)count * sizeof(sel_complex));
    if (owned == NULL) {                              /* GCOVR_EXCL_BR_LINE: allocation cannot be forced */
        for (int index = 0; index < count; index++) { /* GCOVR_EXCL_LINE: allocation-failure path */
            free_compounds(temp[index].compounds, temp[index].count); /* GCOVR_EXCL_LINE */
            PyMem_Free(temp[index].compounds);                        /* GCOVR_EXCL_LINE: allocation-failure path */
        } /* GCOVR_EXCL_LINE: allocation-failure path */
        parser->error = 1; /* GCOVR_EXCL_LINE: allocation-failure path */
        return -1;         /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    memcpy(owned, temp, (size_t)count * sizeof(sel_complex));
    *out_alts = owned;
    *out_count = count;
    return 0;
}

static void selector_free(sel_compiled *compiled) {
    sel_free_alts(compiled->alts, compiled->count);
    PyMem_Free(compiled->source);
    PyMem_Free(compiled);
}

/* Compile a selector string against the tree it will run on. Returns NULL with a
   ValueError set on a syntax error. */
static sel_compiled *selector_compile(th_tree *tree, PyObject *selector_str) {
    sel_compiled *compiled = PyMem_Calloc(1, sizeof(sel_compiled));
    if (compiled == NULL) {              /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return (void *)PyErr_NoMemory(); /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    compiled->source = PyUnicode_AsUCS4Copy(selector_str);
    if (compiled->source == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        PyMem_Free(compiled);       /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;                /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    compiled->quirks = th_tree_quirks(tree);
    compiled->tree = tree;
    sel_parser parser = {compiled->source, 0, PyUnicode_GET_LENGTH(selector_str), tree, 0};
    if (sel_parse_alts(&parser, &compiled->alts, &compiled->count, 0, 0) < 0) {
        PyMem_Free(compiled->source);
        PyMem_Free(compiled);
        PyErr_SetString(PyExc_ValueError, "invalid CSS selector");
        return NULL;
    }
    return compiled;
}

/* --------------------------------------------------------------- matching */

/* Call-scoped context threaded through the matcher: the tree (so :empty can read
   text spans and the state pseudos resolve attributes), the origin element the
   query was invoked on (so :scope can match it), and the quirks flag (so class/ID
   fold case). It is per-call, not per-compile, so it is built fresh by each
   select()/matches()/closest() rather than stored on the cached compiled selector. */
typedef struct {
    th_tree *tree;
    th_node *origin;
    int quirks;
} sel_match_ctx;

/* The functional pseudo-classes recurse into the matcher: :is()/:where() test the
   element against a nested list, and :has() searches for a relative match, so the
   matching primitives they call are forward-declared here. */
static int sel_match_compound(th_node *node, const sel_compound *compound, const sel_match_ctx *ctx);
static int sel_matches_alts(th_node *node, const sel_complex *alts, int count, const sel_match_ctx *ctx);
static int sel_has_match(th_node *anchor, const sel_complex *alts, int count, const sel_match_ctx *ctx);

static Py_UCS4 sel_fold(Py_UCS4 ch, int ci) {
    return (ci && ch >= 'A' && ch <= 'Z') ? ch + 32 : ch;
}

static int sel_eq(const Py_UCS4 *left, Py_ssize_t alen, const Py_UCS4 *right, Py_ssize_t blen, int ci) {
    if (alen != blen) {
        return 0;
    }
    for (Py_ssize_t index = 0; index < alen; index++) {
        if (sel_fold(left[index], ci) != sel_fold(right[index], ci)) {
            return 0;
        }
    }
    return 1;
}

/* Whether a whitespace-separated token list contains the wanted value. */
static int contains_ws_token(const Py_UCS4 *value, Py_ssize_t value_len, const Py_UCS4 *want, Py_ssize_t want_len,
                             int ci) {
    Py_ssize_t cursor = 0;
    while (cursor < value_len) {
        while (cursor < value_len && is_space(value[cursor])) {
            cursor++;
        }
        Py_ssize_t start = cursor;
        while (cursor < value_len && !is_space(value[cursor])) {
            cursor++;
        }
        if (cursor > start && sel_eq(value + start, cursor - start, want, want_len, ci)) {
            return 1;
        }
    }
    return 0;
}

static const th_node_attr *sel_find_attr(th_node *node, uint32_t atom) {
    for (Py_ssize_t index = 0; index < node->attr_count; index++) {
        if (node->attrs[index].name_atom == atom) {
            return &node->attrs[index];
        }
    }
    return NULL;
}

/* Whether the attribute value satisfies the simple's operator and value, folding
   case per ci (the explicit flag combined with the HTML default-set decision). */
static int sel_match_attr_op(const sel_simple *simple, const Py_UCS4 *value, Py_ssize_t value_len, int ci) {
    const Py_UCS4 *want = simple->value;
    Py_ssize_t want_len = simple->value_len;
    switch (simple->op) {
    case OP_EXISTS:
        return 1;
    case OP_EQ:
        return sel_eq(value, value_len, want, want_len, ci);
    case OP_PREFIX:
        return want_len > 0 && value_len >= want_len && sel_eq(value, want_len, want, want_len, ci);
    case OP_SUFFIX:
        return want_len > 0 && value_len >= want_len &&
               sel_eq(value + (value_len - want_len), want_len, want, want_len, ci);
    case OP_DASH:
        return sel_eq(value, value_len, want, want_len, ci) ||
               (value_len > want_len && value[want_len] == '-' && sel_eq(value, want_len, want, want_len, ci));
    case OP_INCLUDE: {
        if (want_len == 0) {
            return 0;
        }
        return contains_ws_token(value, value_len, want, want_len, ci);
    }
    default: /* OP_SUBSTR */
        if (want_len == 0) {
            return 0;
        }
        for (Py_ssize_t start = 0; start + want_len <= value_len; start++) {
            if (sel_eq(value + start, want_len, want, want_len, ci)) {
                return 1;
            }
        }
        return 0;
    }
}

/* Two elements share a type when their namespace and tag match; a custom tag
   (no builtin atom) compares by lowercased name so distinct customs stay apart. */
static int sel_same_type(const th_node *a, const th_node *b) {
    if (a->ns != b->ns || a->atom != b->atom) {
        return 0;
    }
    if (a->atom != TH_TAG_UNKNOWN) {
        return 1;
    }
    return sel_eq(a->text, a->text_len, b->text, b->text_len, 0);
}

/* Whether node has no element sibling on the chosen side (next when from_end),
   counting only same-type siblings when of_type. Drives the first/last/only
   structural pseudo-classes. */
static int sel_no_sibling(th_node *node, int from_end, int of_type) {
    for (th_node *sibling = from_end ? node->next_sibling : node->prev_sibling; sibling != NULL;
         sibling = from_end ? sibling->next_sibling : sibling->prev_sibling) {
        if (sibling->type == TH_NODE_ELEMENT && (!of_type || sel_same_type(node, sibling))) {
            return 0;
        }
    }
    return 1;
}

/* The 1-based position of node among its element siblings (from the end when
   from_end), counting only same-type siblings when of_type. */
static int sel_sibling_index(th_node *node, int from_end, int of_type) {
    int index = 1;
    for (th_node *sibling = from_end ? node->next_sibling : node->prev_sibling; sibling != NULL;
         sibling = from_end ? sibling->next_sibling : sibling->prev_sibling) {
        if (sibling->type == TH_NODE_ELEMENT && (!of_type || sel_same_type(node, sibling))) {
            index++;
        }
    }
    return index;
}

/* Whether a 1-based index satisfies An+B for some non-negative n. */
static int sel_nth_matches(int a, int b, int index) {
    if (a == 0) {
        return index == b;
    }
    int diff = index - b;
    return diff % a == 0 && diff / a >= 0;
}

/* An element is :empty (Selectors-4 §13.2) when it has no children except,
   optionally, document white space: any element child or a text child holding a
   non-whitespace code point makes it non-empty, while comments, processing
   instructions, and whitespace-only text do not count. Level 3 rejected
   whitespace-only elements; Level 4 changed that, so `<p> </p>` now matches. */
static int sel_is_empty(const th_node *node, th_tree *tree) {
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        if (child->type == TH_NODE_ELEMENT) {
            return 0;
        }
        if (child->type == TH_NODE_TEXT && !th_node_text_is_blank(tree, child)) {
            return 0;
        }
    }
    return 1;
}

/* ---- state pseudo-classes (Selectors-4 §11/§12): all statically determinable
   from attributes and structure, so they read the parsed tree directly ---- */

static int sel_has_attr(th_node *node, uint32_t atom) {
    return sel_find_attr(node, atom) != NULL;
}

/* A node's tag atom when it is an HTML element, else TH_TAG_UNKNOWN. Folding the
   namespace test into the atom lookup keeps the form-control checks a single
   compare (a foreign or non-element node never equals a control atom) and avoids
   the namespace clause on every check. */
static uint16_t sel_html_atom(const th_node *node) {
    return node->ns == TH_NS_HTML ? node->atom : TH_TAG_UNKNOWN;
}

/* Whether node is an HTML element whose tag atom is one of count entries in set. */
static int sel_atom_in_set(const th_node *node, const uint16_t *set, size_t count) {
    if (node->ns != TH_NS_HTML) {
        return 0;
    }
    for (size_t index = 0; index < count; index++) {
        if (node->atom == set[index]) {
            return 1;
        }
    }
    return 0;
}

/* Whether an <input>'s type keyword is one of count entries in types; a missing or
   empty type attribute behaves as type="text" (HTML invalid-value default). */
static int sel_input_type_in(th_node *node, const char *const *types, size_t count) {
    static const Py_UCS4 text_default[] = {'t', 'e', 'x', 't'};
    const th_node_attr *attr = sel_find_attr(node, TH_ATTR_TYPE);
    const Py_UCS4 *value = text_default;
    Py_ssize_t value_len = 4;
    /* a parsed attribute stores an empty value as NULL, so value != NULL means a
       non-empty type; a missing or empty type keeps the "text" default */
    if (attr != NULL && attr->value != NULL) {
        value = attr->value;
        value_len = attr->value_len;
    }
    for (size_t index = 0; index < count; index++) {
        if (sel_kw(value, value_len, types[index])) {
            return 1;
        }
    }
    return 0;
}

/* Whether node sits within fieldset's first <legend> child (the carve-out that
   keeps a control enabled even when an ancestor fieldset is disabled). */
static int sel_in_first_legend(const th_node *node, const th_node *fieldset) {
    const th_node *legend = NULL;
    for (const th_node *child = fieldset->first_child; child != NULL; child = child->next_sibling) {
        if (sel_html_atom(child) == TH_TAG_LEGEND) { /* a non-element child has atom UNKNOWN, never LEGEND */
            legend = child;
            break;
        }
    }
    if (legend == NULL) {
        return 0;
    }
    /* node is always a descendant of fieldset (the caller found fieldset by walking
       node's ancestors), so the walk reaches fieldset before running off the top */
    for (const th_node *ancestor = node; ancestor != fieldset; ancestor = ancestor->parent) {
        if (ancestor == legend) {
            return 1;
        }
    }
    return 0;
}

/* The "actually disabled" predicate (HTML form-control infrastructure). */
static int sel_is_disabled(th_node *node) {
    static const uint16_t FORM_CONTROLS[] = {TH_TAG_BUTTON, TH_TAG_INPUT, TH_TAG_SELECT, TH_TAG_TEXTAREA};
    uint16_t atom = sel_html_atom(node);
    if (atom == TH_TAG_OPTGROUP || atom == TH_TAG_FIELDSET) {
        return sel_has_attr(node, TH_ATTR_DISABLED);
    }
    if (atom == TH_TAG_OPTION) {
        return sel_has_attr(node, TH_ATTR_DISABLED) ||
               (sel_html_atom(node->parent) == TH_TAG_OPTGROUP && sel_has_attr(node->parent, TH_ATTR_DISABLED));
    }
    if (!sel_atom_in_set(node, FORM_CONTROLS, sizeof(FORM_CONTROLS) / sizeof(FORM_CONTROLS[0]))) {
        return 0; /* a foreign or non-control element is never disabled */
    }
    if (sel_has_attr(node, TH_ATTR_DISABLED)) {
        return 1;
    }
    for (th_node *ancestor = node->parent; ancestor != NULL; ancestor = ancestor->parent) {
        if (sel_html_atom(ancestor) == TH_TAG_FIELDSET && sel_has_attr(ancestor, TH_ATTR_DISABLED) &&
            !sel_in_first_legend(node, ancestor)) {
            return 1;
        }
    }
    return 0;
}

static int sel_is_enabled(th_node *node) {
    static const uint16_t ENABLEABLE[] = {TH_TAG_BUTTON,   TH_TAG_INPUT,  TH_TAG_SELECT,  TH_TAG_TEXTAREA,
                                          TH_TAG_OPTGROUP, TH_TAG_OPTION, TH_TAG_FIELDSET};
    return sel_atom_in_set(node, ENABLEABLE, sizeof(ENABLEABLE) / sizeof(ENABLEABLE[0])) && !sel_is_disabled(node);
}

/* :checked / :default share their static form: a checkbox/radio with the checked
   content attribute, or an option with the selected content attribute. */
static int sel_is_checked(th_node *node) {
    static const char *const TOGGLE_TYPES[] = {"checkbox", "radio"};
    uint16_t atom = sel_html_atom(node);
    if (atom == TH_TAG_OPTION) {
        return sel_has_attr(node, TH_ATTR_SELECTED);
    }
    if (atom == TH_TAG_INPUT) {
        return sel_input_type_in(node, TOGGLE_TYPES, 2) && sel_has_attr(node, TH_ATTR_CHECKED);
    }
    return 0;
}

static int sel_is_required_candidate(const th_node *node) {
    static const uint16_t SET[] = {TH_TAG_INPUT, TH_TAG_SELECT, TH_TAG_TEXTAREA};
    return sel_atom_in_set(node, SET, sizeof(SET) / sizeof(SET[0]));
}

/* Whether node is an editing host: the nearest self-or-ancestor carrying a
   contenteditable attribute resolves to the "true" state (value "" or "true");
   "false" stops inheritance, an invalid value keeps walking up. */
static int sel_is_editable(th_node *node) {
    /* the document and other ancestors carry no contenteditable attribute, so the
       walk simply runs to the top; sel_find_attr returns NULL for a non-element */
    for (th_node *current = node; current != NULL; current = current->parent) {
        const th_node_attr *attr = sel_find_attr(current, TH_ATTR_CONTENTEDITABLE);
        if (attr == NULL) {
            continue;
        }
        /* an empty value is stored as NULL, and both the empty and "true" states make
           the element editable */
        if (attr->value == NULL || sel_kw(attr->value, attr->value_len, "true")) {
            return 1;
        }
        if (sel_kw(attr->value, attr->value_len, "false")) {
            return 0;
        }
    }
    return 0;
}

static int sel_is_readwrite(th_node *node) {
    static const char *const MUTABLE_TYPES[] = {"text", "search", "url",  "tel",  "email",          "password",
                                                "date", "month",  "week", "time", "datetime-local", "number"};
    uint16_t atom = sel_html_atom(node);
    if (atom == TH_TAG_TEXTAREA) {
        return !sel_has_attr(node, TH_ATTR_READONLY) && !sel_is_disabled(node);
    }
    if (atom == TH_TAG_INPUT) {
        if (!sel_input_type_in(node, MUTABLE_TYPES, sizeof(MUTABLE_TYPES) / sizeof(MUTABLE_TYPES[0]))) {
            return 0; /* a non-text input (checkbox, button, ...) is never read-write */
        }
        return !sel_has_attr(node, TH_ATTR_READONLY) && !sel_is_disabled(node);
    }
    return sel_is_editable(node);
}

/* The nearest self-or-ancestor element carrying attribute atom, or NULL. */
static const th_node_attr *sel_ancestor_attr(th_node *node, uint32_t atom) {
    for (th_node *current = node; current != NULL; current = current->parent) {
        const th_node_attr *attr = sel_find_attr(current, atom);
        if (attr != NULL) {
            return attr;
        }
    }
    return NULL;
}

/* :dir(ltr|rtl) against the nearest dir attribute (want is 1=ltr, 2=rtl, 0=other).
   dir="auto" and invalid values establish no statically resolvable direction. */
static int sel_dir_matches(th_node *node, int want) {
    const th_node_attr *attr = sel_ancestor_attr(node, TH_ATTR_DIR);
    if (attr == NULL) {
        return 0;
    }
    /* an empty dir value is stored as NULL/length 0, which sel_kw rejects below */
    if (sel_kw(attr->value, attr->value_len, "ltr")) {
        return want == 1;
    }
    if (sel_kw(attr->value, attr->value_len, "rtl")) {
        return want == 2;
    }
    return 0;
}

/* RFC 4647 basic filtering of one language range against a language tag. */
static int sel_lang_range_matches(const Py_UCS4 *lang, Py_ssize_t lang_len, const Py_UCS4 *range,
                                  Py_ssize_t range_len) {
    if (range_len == 1 && range[0] == '*') {
        return lang_len > 0;
    }
    if (lang_len < range_len || !sel_eq(lang, range_len, range, range_len, 1)) {
        return 0;
    }
    return lang_len == range_len || lang[range_len] == '-';
}

/* :lang(...) against the nearest lang attribute, matching any comma-separated range
   stored in simple->name (each an identifier, a quoted string, or *). */
static int sel_lang_matches(th_node *node, const sel_simple *simple) {
    const th_node_attr *attr = sel_ancestor_attr(node, TH_ATTR_LANG);
    if (attr == NULL) {
        return 0;
    }
    /* an empty lang value (stored as NULL/length 0) matches no range below */
    Py_ssize_t pos = 0;
    while (pos < simple->name_len) {
        while (pos < simple->name_len && (is_space(simple->name[pos]) || simple->name[pos] == ',')) {
            pos++;
        }
        Py_ssize_t start = pos;
        while (pos < simple->name_len && simple->name[pos] != ',') {
            pos++;
        }
        Py_ssize_t end = pos;
        while (end > start && is_space(simple->name[end - 1])) {
            end--;
        }
        const Py_UCS4 *token = simple->name + start;
        Py_ssize_t token_len = end - start;
        if (token_len >= 2 && (token[0] == '"' || token[0] == '\'') && token[token_len - 1] == token[0]) {
            token++;
            token_len -= 2;
        }
        if (token_len > 0 && sel_lang_range_matches(attr->value, attr->value_len, token, token_len)) {
            return 1;
        }
    }
    return 0;
}

static int sel_match_pseudo(th_node *node, const sel_simple *simple, const sel_match_ctx *ctx) {
    switch (simple->pseudo) { /* GCOVR_EXCL_BR_LINE: the parser only stores known pseudo ids */
    case PSEUDO_ROOT:
        /* the root element's parent is the document, never an element (a matched
           node always has a parent, as the '>' combinator above relies on) */
        return node->parent->type != TH_NODE_ELEMENT;
    case PSEUDO_EMPTY:
        return sel_is_empty(node, ctx->tree);
    case PSEUDO_FIRST_CHILD:
        return sel_no_sibling(node, 0, 0);
    case PSEUDO_LAST_CHILD:
        return sel_no_sibling(node, 1, 0);
    case PSEUDO_ONLY_CHILD:
        return sel_no_sibling(node, 0, 0) && sel_no_sibling(node, 1, 0);
    case PSEUDO_FIRST_OF_TYPE:
        return sel_no_sibling(node, 0, 1);
    case PSEUDO_LAST_OF_TYPE:
        return sel_no_sibling(node, 1, 1);
    case PSEUDO_ONLY_OF_TYPE:
        return sel_no_sibling(node, 0, 1) && sel_no_sibling(node, 1, 1);
    case PSEUDO_NTH_CHILD:
        return sel_nth_matches(simple->nth_a, simple->nth_b, sel_sibling_index(node, 0, 0));
    case PSEUDO_NTH_LAST_CHILD:
        return sel_nth_matches(simple->nth_a, simple->nth_b, sel_sibling_index(node, 1, 0));
    case PSEUDO_NTH_OF_TYPE:
        return sel_nth_matches(simple->nth_a, simple->nth_b, sel_sibling_index(node, 0, 1));
    case PSEUDO_NTH_LAST_OF_TYPE:
        return sel_nth_matches(simple->nth_a, simple->nth_b, sel_sibling_index(node, 1, 1));
    /* the functional pseudo-classes: :is()/:where() match the element against the
       nested list; :not() is its negation; :has() searches for a relative match
       anchored at it */
    case PSEUDO_IS:
    case PSEUDO_WHERE:
        return sel_matches_alts(node, simple->sub, simple->sub_count, ctx);
    case PSEUDO_NOT:
        return !sel_matches_alts(node, simple->sub, simple->sub_count, ctx);
    case PSEUDO_HAS:
        return sel_has_match(node, simple->sub, simple->sub_count, ctx);
    /* state pseudo-classes (Selectors-4 §11/§12) read attributes and structure */
    case PSEUDO_SCOPE:
        return node == ctx->origin;
    case PSEUDO_CHECKED:
        return sel_is_checked(node);
    case PSEUDO_DISABLED:
        return sel_is_disabled(node);
    case PSEUDO_ENABLED:
        return sel_is_enabled(node);
    case PSEUDO_REQUIRED:
        return sel_is_required_candidate(node) && sel_has_attr(node, TH_ATTR_REQUIRED);
    case PSEUDO_OPTIONAL:
        return sel_is_required_candidate(node) && !sel_has_attr(node, TH_ATTR_REQUIRED);
    case PSEUDO_READ_ONLY:
        return !sel_is_readwrite(node);
    case PSEUDO_READ_WRITE:
        return sel_is_readwrite(node);
    case PSEUDO_DEFAULT:
        /* the statically-knowable defaults; a form's default submit button needs
           form-owner association a static tree does not model */
        return sel_is_checked(node);
    case PSEUDO_LANG:
        return sel_lang_matches(node, simple);
    case PSEUDO_DIR:
        return sel_dir_matches(node, simple->nth_a);
    default: /* PSEUDO_NEVER: live UA/interaction state never holds in a static tree */
        return 0;
    }
}

static int sel_match_simple(th_node *node, const sel_simple *simple, const sel_match_ctx *ctx) {
    switch (simple->kind) {
    case '*':
        return 1;
    case ':':
        return sel_match_pseudo(node, simple, ctx);
    case 'e':
        if (simple->tag_atom != TH_TAG_UNKNOWN) {
            return node->atom == simple->tag_atom;
        }
        /* a custom/unknown tag is stored lowercased; type selectors are ASCII case-insensitive
           in HTML, so match it case-insensitively like the builtin-atom path above does */
        return sel_eq(node->text, node->text_len, simple->name, simple->name_len, 1);
    case '#': {
        /* class/ID selectors are case-sensitive in no-quirks mode, ASCII
           case-insensitive in quirks mode (Selectors-4 §6.1/§6.2) */
        const th_node_attr *attr = sel_find_attr(node, TH_ATTR_ID);
        return attr != NULL && attr->value != NULL &&
               sel_eq(attr->value, attr->value_len, simple->name, simple->name_len, ctx->quirks);
    }
    case '.': {
        const th_node_attr *attr = sel_find_attr(node, TH_ATTR_CLASS);
        if (attr == NULL || attr->value == NULL) {
            return 0;
        }
        return contains_ws_token(attr->value, attr->value_len, simple->name, simple->name_len, ctx->quirks);
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
        /* the HTML case-insensitive set applies only to HTML-namespace elements */
        int ci = simple->ci || (simple->ci_default && node->ns == TH_NS_HTML);
        return sel_match_attr_op(simple, value, value_len, ci);
    }
    }
}

static int sel_match_compound(th_node *node, const sel_compound *compound, const sel_match_ctx *ctx) {
    if (node->type != TH_NODE_ELEMENT) {
        return 0;
    }
    for (int index = 0; index < compound->count; index++) {
        if (!sel_match_simple(node, &compound->simples[index], ctx)) {
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

/* node matches compounds[index]; verify the combinators and compounds to its left,
   with backtracking on the descendant and general-sibling axes. anchor is NULL for an
   ordinary selector (the leftmost compound is the end); for a :has() relative selector
   it is the element :has() tests, and the leftmost compound's leading combinator must
   connect to it. The interior-combinator machinery is shared by both. */
static int sel_match_from(th_node *node, const sel_complex *complex, int index, th_node *anchor,
                          const sel_match_ctx *ctx) {
    if (index == 0) {
        if (anchor == NULL) {
            return 1;
        }
        switch (complex->compounds[0].combinator) {
        case '>':
            return node->parent == anchor;
        case '+':
            return sel_prev_element(node) == anchor;
        case '~':
            for (th_node *prev = sel_prev_element(node); prev != NULL; prev = sel_prev_element(prev)) {
                if (prev == anchor) {
                    return 1;
                }
            }
            return 0;
        default: /* descendant */
            for (th_node *ancestor = node->parent; ancestor != NULL; ancestor = ancestor->parent) {
                if (ancestor == anchor) {
                    return 1;
                }
            }
            return 0;
        }
    }
    const sel_compound *target = &complex->compounds[index - 1];
    switch (complex->compounds[index].combinator) {
    case '>': {
        /* a matched node is an element, so it always has a parent (the document
           at the root), which sel_match_compound rejects as a non-element */
        th_node *parent = node->parent;
        return sel_match_compound(parent, target, ctx) && sel_match_from(parent, complex, index - 1, anchor, ctx);
    }
    case '+': {
        th_node *prev = sel_prev_element(node);
        return prev != NULL && sel_match_compound(prev, target, ctx) &&
               sel_match_from(prev, complex, index - 1, anchor, ctx);
    }
    case '~':
        for (th_node *prev = sel_prev_element(node); prev != NULL; prev = sel_prev_element(prev)) {
            if (sel_match_compound(prev, target, ctx) && sel_match_from(prev, complex, index - 1, anchor, ctx)) {
                return 1;
            }
        }
        return 0;
    default: /* descendant */
        for (th_node *ancestor = node->parent; ancestor != NULL; ancestor = ancestor->parent) {
            if (sel_match_compound(ancestor, target, ctx) &&
                sel_match_from(ancestor, complex, index - 1, anchor, ctx)) {
                return 1;
            }
        }
        return 0;
    }
}

/* node matches some alternative in alts: it is the subject (rightmost compound) of
   one complex whose combinators to the left verify. The top-level match and the
   :is()/:where() pseudo-classes share this. */
static int sel_matches_alts(th_node *node, const sel_complex *alts, int count, const sel_match_ctx *ctx) {
    for (int index = 0; index < count; index++) {
        const sel_complex *complex = &alts[index];
        int subject = complex->count - 1;
        if (sel_match_compound(node, &complex->compounds[subject], ctx) &&
            sel_match_from(node, complex, subject, NULL, ctx)) {
            return 1;
        }
    }
    return 0;
}

/* Whether any element in the subtree below node is the subject of rel anchored at
   anchor (the element :has() is testing), checked recursively in document order. */
static int sel_has_subtree(th_node *node, const sel_complex *rel, int subject, th_node *anchor,
                           const sel_match_ctx *ctx) {
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        if (child->type != TH_NODE_ELEMENT) {
            continue;
        }
        if ((sel_match_compound(child, &rel->compounds[subject], ctx) &&
             sel_match_from(child, rel, subject, anchor, ctx)) ||
            sel_has_subtree(child, rel, subject, anchor, ctx)) {
            return 1;
        }
    }
    return 0;
}

/* Whether the anchor element satisfies any :has() relative selector. A relative
   selector reaches the anchor's descendants and, through a leading sibling
   combinator, its following siblings and their subtrees. */
static int sel_has_match(th_node *anchor, const sel_complex *alts, int count, const sel_match_ctx *ctx) {
    for (int index = 0; index < count; index++) {
        const sel_complex *rel = &alts[index];
        int subject = rel->count - 1;
        if (sel_has_subtree(anchor, rel, subject, anchor, ctx)) {
            return 1;
        }
        /* only a leading sibling combinator (:has(+ x) / :has(~ x)) can match outside
           the anchor's subtree; a descendant or child relative selector cannot, so its
           following-sibling scan would always fail and is skipped */
        char lead = rel->compounds[0].combinator;
        if (lead != '+' && lead != '~') {
            continue;
        }
        for (th_node *sibling = anchor->next_sibling; sibling != NULL; sibling = sibling->next_sibling) {
            if (sibling->type != TH_NODE_ELEMENT) {
                continue;
            }
            if ((sel_match_compound(sibling, &rel->compounds[subject], ctx) &&
                 sel_match_from(sibling, rel, subject, anchor, ctx)) ||
                sel_has_subtree(sibling, rel, subject, anchor, ctx)) {
                return 1;
            }
        }
    }
    return 0;
}

static int selector_matches(th_node *node, const sel_compiled *compiled, th_node *origin) {
    sel_match_ctx ctx = {compiled->tree, origin, compiled->quirks};
    return sel_matches_alts(node, compiled->alts, compiled->count, &ctx);
}

/* The lone simple selector of a selector that is one group, one compound, one
   simple (such as "a", ".x", or "#id"), or NULL otherwise. The caller can then
   test each element with sel_match_simple directly, skipping the group and
   combinator machinery. */
static const sel_simple *sel_single_simple(const sel_compiled *compiled) {
    if (compiled->count == 1 && compiled->alts[0].count == 1 && compiled->alts[0].compounds[0].count == 1) {
        return &compiled->alts[0].compounds[0].simples[0];
    }
    return NULL;
}

#endif /* TURBOHTML_SELECTOR_H */
