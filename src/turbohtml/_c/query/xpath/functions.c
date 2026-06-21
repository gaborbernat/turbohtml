/* The XPath 1.0 core function library plus the EXSLT regular-expression extensions
   parsel and scrapy lean on, and the Python hook the parser conformance tests call. */

#include "core/common.h"
#include "dom/tree.h"
#include "query/xpath/internal.h"
#include "query/xpath/xpath.h"

#include <math.h>
#include <string.h>

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
    if (attr == -2) {
        return ucs4_from_ascii(XP_XML_NS_PREFIX, sizeof(XP_XML_NS_PREFIX) - 1, len);
    }
    if (attr >= 0) {
        Py_ssize_t blen;
        const char *bytes = th_attr_name(ctx->tree, node->attrs[attr].name_atom, &blen);
        Py_UCS4 *buffer = ucs4_from_ascii(bytes, blen, len);
        if (buffer == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
            return NULL;      /* GCOVR_EXCL_LINE */
        }
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

/* namespace-uri(): empty for HTML elements, attributes, namespace nodes, and
   non-elements; the foreign-content URI for an SVG or MathML element. */
static Py_UCS4 *node_namespace_uri(xp_ctx *ctx, xp_result *args, int argc, Py_ssize_t *len) {
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
    const char *uri = "";
    Py_ssize_t uri_len = 0;
    if (attr == -1 && node->type == TH_NODE_ELEMENT) {
        if (node->ns == TH_NS_SVG) {
            uri = XP_SVG_NS_URI;
            uri_len = sizeof(XP_SVG_NS_URI) - 1;
        } else if (node->ns == TH_NS_MATHML) {
            uri = XP_MATHML_NS_URI;
            uri_len = sizeof(XP_MATHML_NS_URI) - 1;
        }
    }
    return ucs4_from_ascii(uri, uri_len, len);
}

/* RFC 4647 prefix match, ASCII case-insensitive: the tag equals the wanted code
   or extends it with a "-subtag" suffix (so "en" matches "en" and "en-US"). */
static int lang_tag_matches(const Py_UCS4 *tag, Py_ssize_t tag_len, const Py_UCS4 *want, Py_ssize_t want_len) {
    if (tag_len < want_len) {
        return 0;
    }
    for (Py_ssize_t index = 0; index < want_len; index++) {
        Py_UCS4 in_tag = tag[index] >= 'A' && tag[index] <= 'Z' ? tag[index] + 32 : tag[index];
        Py_UCS4 in_want = want[index] >= 'A' && want[index] <= 'Z' ? want[index] + 32 : want[index];
        if (in_tag != in_want) {
            return 0;
        }
    }
    return tag_len == want_len || tag[want_len] == '-';
}

/* lang(): true when the nearest self-or-ancestor element carrying a lang
   attribute names a language the wanted code is a prefix of. */
static int node_lang(xp_ctx *ctx, xp_result *arg) {
    Py_ssize_t want_len;
    Py_UCS4 *want = to_string(ctx->tree, arg, &want_len);
    if (want == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        return -1;      /* GCOVR_EXCL_LINE */
    }
    int result = 0;
    for (struct th_node *node = ctx->node; node != NULL; node = node->parent) {
        const th_node_attr *lang_attr = NULL;
        for (Py_ssize_t index = 0; index < node->attr_count; index++) {
            if (node->attrs[index].name_atom == TH_ATTR_LANG) {
                lang_attr = &node->attrs[index];
                break;
            }
        }
        if (lang_attr != NULL) {
            result = lang_tag_matches(lang_attr->value, lang_attr->value_len, want, want_len);
            break;
        }
    }
    PyMem_Free(want);
    return result;
}

/* True when `token` appears as a whitespace-delimited entry in `list`. */
static int token_in_list(const Py_UCS4 *list, Py_ssize_t list_len, const Py_UCS4 *token, Py_ssize_t token_len) {
    if (token_len == 0) {
        return 0;
    }
    Py_ssize_t index = 0;
    while (index < list_len) {
        while (index < list_len && xp_is_space(list[index])) {
            index++;
        }
        Py_ssize_t start = index;
        while (index < list_len && !xp_is_space(list[index])) {
            index++;
        }
        if (index - start == token_len && memcmp(list + start, token, (size_t)token_len * sizeof(Py_UCS4)) == 0) {
            return 1;
        }
    }
    return 0;
}

/* id(object): the elements whose id attribute is one of the whitespace-separated
   tokens in the argument's string-value (a node-set argument contributes the
   string-value of each member). */
static int eval_id(xp_ctx *ctx, xp_result *arg, xp_result *out) {
    memset(out, 0, sizeof(*out));
    out->kind = XP_NODESET;
    Py_UCS4 *list = NULL;
    Py_ssize_t list_len = 0;
    if (arg->kind == XP_NODESET) {
        for (Py_ssize_t index = 0; index < arg->nodes.len; index++) {
            Py_ssize_t each;
            Py_UCS4 *text = item_string(ctx->tree, arg->nodes.items[index], &each);
            if (text == NULL) {   /* GCOVR_EXCL_BR_LINE: alloc */
                PyMem_Free(list); /* GCOVR_EXCL_LINE */
                return -1;        /* GCOVR_EXCL_LINE */
            }
            Py_UCS4 *grown = PyMem_Realloc(list, (size_t)(list_len + each + 1) * sizeof(Py_UCS4));
            if (grown == NULL) {  /* GCOVR_EXCL_BR_LINE: alloc */
                PyMem_Free(text); /* GCOVR_EXCL_LINE */
                PyMem_Free(list); /* GCOVR_EXCL_LINE */
                return -1;        /* GCOVR_EXCL_LINE */
            }
            list = grown;
            list[list_len++] = ' ';
            memcpy(list + list_len, text, (size_t)each * sizeof(Py_UCS4));
            list_len += each;
            PyMem_Free(text);
        }
    } else {
        list = to_string(ctx->tree, arg, &list_len);
        if (list == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
            return -1;      /* GCOVR_EXCL_LINE */
        }
    }
    int rc = 0;
    for (struct th_node *node = th_tree_document(ctx->tree); node != NULL; node = document_next(node)) {
        if (node->type != TH_NODE_ELEMENT) {
            continue;
        }
        for (Py_ssize_t index = 0; index < node->attr_count; index++) {
            if (node->attrs[index].name_atom == TH_ATTR_ID &&
                token_in_list(list, list_len, node->attrs[index].value, node->attrs[index].value_len)) {
                if (ns_push(&out->nodes, node, -1) < 0) { /* GCOVR_EXCL_BR_LINE: alloc */
                    rc = -1;                              /* GCOVR_EXCL_LINE */
                } /* GCOVR_EXCL_LINE: brace of the never-taken alloc-failure branch */
                break;
            }
        }
    }
    PyMem_Free(list);
    if (rc < 0) {                     /* GCOVR_EXCL_BR_LINE: alloc */
        xp_nodeset_free(&out->nodes); /* GCOVR_EXCL_LINE */
    } /* GCOVR_EXCL_LINE: brace of the never-taken alloc-failure branch */
    return rc;
}

/* --- EXSLT regular-expression functions (re:test / re:replace) ------------ */
/* parsel and scrapy lean on these, so the engine borrows Python's re module.
   Evaluation runs inside the tree's critical section, but re touches no turbohtml
   handle, so the call cannot deadlock against it. */

/* Build a Python pattern string, folding the EXSLT flag letters into an inline
   "(?imsx)" group and reporting a 'g' (global) flag through *global. NULL with an
   exception set on failure. */
static PyObject *exslt_pattern(struct th_tree *tree, xp_result *pattern_arg, xp_result *flags_arg, int *global) {
    *global = 0;
    Py_ssize_t pat_len;
    Py_UCS4 *pattern = to_string(tree, pattern_arg, &pat_len);
    if (pattern == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        return NULL;       /* GCOVR_EXCL_LINE */
    }
    Py_UCS4 inline_flags[4];
    Py_ssize_t flag_count = 0;
    if (flags_arg != NULL) {
        Py_ssize_t flag_len;
        Py_UCS4 *flags = to_string(tree, flags_arg, &flag_len);
        if (flags == NULL) {     /* GCOVR_EXCL_BR_LINE: alloc */
            PyMem_Free(pattern); /* GCOVR_EXCL_LINE */
            return NULL;         /* GCOVR_EXCL_LINE */
        }
        for (Py_ssize_t index = 0; index < flag_len; index++) {
            Py_UCS4 letter = flags[index];
            if (letter == 'g') {
                *global = 1;
            } else if (letter == 'i' || letter == 'm' || letter == 's' || letter == 'x') {
                inline_flags[flag_count++] = letter;
            }
        }
        PyMem_Free(flags);
    }
    Py_ssize_t prefix_len = flag_count > 0 ? flag_count + 3 : 0; /* "(?" flags ")" */
    Py_UCS4 *buf = PyMem_Malloc((size_t)(prefix_len + pat_len) * sizeof(Py_UCS4));
    if (buf == NULL) {       /* GCOVR_EXCL_BR_LINE: alloc */
        PyMem_Free(pattern); /* GCOVR_EXCL_LINE */
        return NULL;         /* GCOVR_EXCL_LINE */
    }
    Py_ssize_t write = 0;
    if (flag_count > 0) {
        buf[write++] = '(';
        buf[write++] = '?';
        for (Py_ssize_t index = 0; index < flag_count; index++) {
            buf[write++] = inline_flags[index];
        }
        buf[write++] = ')';
    }
    memcpy(buf + write, pattern, (size_t)pat_len * sizeof(Py_UCS4));
    PyMem_Free(pattern);
    PyObject *result = PyUnicode_FromKindAndData(PyUnicode_4BYTE_KIND, buf, prefix_len + pat_len);
    PyMem_Free(buf);
    return result;
}

/* re:test(input, regex, flags?): true when the regex matches anywhere in input. */
static int exslt_re_test(struct th_tree *tree, xp_result *args, int argc, xp_result *out) {
    int global;
    PyObject *pattern = exslt_pattern(tree, &args[1], argc >= 3 ? &args[2] : NULL, &global);
    Py_ssize_t input_len;
    Py_UCS4 *input_text = to_string(tree, &args[0], &input_len);
    if (pattern == NULL || input_text == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        Py_XDECREF(pattern);                     /* GCOVR_EXCL_LINE */
        PyMem_Free(input_text);                  /* GCOVR_EXCL_LINE */
        return -1;                               /* GCOVR_EXCL_LINE */
    }
    PyObject *input = PyUnicode_FromKindAndData(PyUnicode_4BYTE_KIND, input_text, input_len);
    PyMem_Free(input_text);
    PyObject *re_module = PyImport_ImportModule("re");
    if (input == NULL || re_module == NULL) { /* GCOVR_EXCL_BR_LINE: a UCS-4 alloc or re import cannot be forced */
        Py_XDECREF(input);                    /* GCOVR_EXCL_LINE */
        Py_XDECREF(re_module);                /* GCOVR_EXCL_LINE */
        Py_DECREF(pattern);                   /* GCOVR_EXCL_LINE */
        return -1;                            /* GCOVR_EXCL_LINE */
    }
    PyObject *match = PyObject_CallMethod(re_module, "search", "OO", pattern, input);
    Py_DECREF(re_module);
    Py_DECREF(input);
    Py_DECREF(pattern);
    if (match == NULL) {
        return -1; /* a malformed pattern set re.error */
    }
    result_bool(out, match != Py_None);
    Py_DECREF(match);
    return 0;
}

/* re:replace(input, regex, flags, replacement): substitute matches, all of them
   under a 'g' flag, otherwise the first. */
static int exslt_re_replace(struct th_tree *tree, xp_result *args, xp_result *out) {
    int global;
    PyObject *pattern = exslt_pattern(tree, &args[1], &args[2], &global);
    Py_ssize_t input_len;
    Py_ssize_t repl_len;
    Py_UCS4 *input_text = to_string(tree, &args[0], &input_len);
    Py_UCS4 *repl_text = to_string(tree, &args[3], &repl_len);
    PyObject *input = NULL;
    PyObject *repl = NULL;
    PyObject *re_module = NULL;
    if (pattern != NULL && input_text != NULL && repl_text != NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        input = PyUnicode_FromKindAndData(PyUnicode_4BYTE_KIND, input_text, input_len);
        repl = PyUnicode_FromKindAndData(PyUnicode_4BYTE_KIND, repl_text, repl_len);
        re_module = PyImport_ImportModule("re");
    }
    PyMem_Free(input_text);
    PyMem_Free(repl_text);
    if (pattern == NULL || input == NULL || repl == NULL || re_module == NULL) { /* GCOVR_EXCL_BR_LINE: alloc/import */
        Py_XDECREF(pattern);                                                     /* GCOVR_EXCL_LINE */
        Py_XDECREF(input);                                                       /* GCOVR_EXCL_LINE */
        Py_XDECREF(repl);                                                        /* GCOVR_EXCL_LINE */
        Py_XDECREF(re_module);                                                   /* GCOVR_EXCL_LINE */
        return -1;                                                               /* GCOVR_EXCL_LINE */
    }
    /* count is keyword-only since 3.13; 0 replaces every match, 1 only the first */
    PyObject *call_args = Py_BuildValue("(OOO)", pattern, repl, input);
    PyObject *call_kwargs = Py_BuildValue("{s:i}", "count", global ? 0 : 1);
    PyObject *re_sub = PyObject_GetAttrString(re_module, "sub");
    Py_DECREF(re_module);
    Py_DECREF(input);
    Py_DECREF(repl);
    Py_DECREF(pattern);
    PyObject *replaced = NULL;
    if (call_args != NULL && call_kwargs != NULL && re_sub != NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        replaced = PyObject_Call(re_sub, call_args, call_kwargs);
    }
    Py_XDECREF(call_args);
    Py_XDECREF(call_kwargs);
    Py_XDECREF(re_sub);
    if (replaced == NULL) {
        return -1; /* a malformed pattern set re.error */
    }
    Py_ssize_t result_len = PyUnicode_GET_LENGTH(replaced);
    Py_UCS4 *buf = PyUnicode_AsUCS4Copy(replaced);
    Py_DECREF(replaced);
    if (buf == NULL) { /* GCOVR_EXCL_BR_LINE: alloc */
        return -1;     /* GCOVR_EXCL_LINE */
    }
    result_string(out, buf, result_len);
    return 0;
}

int eval_function(const xp_program *prog, int32_t idx, xp_ctx *ctx, xp_result *out) {
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
    } else if (func_is(fn, "namespace-uri")) {
        Py_ssize_t length;
        Py_UCS4 *text = node_namespace_uri(ctx, args, argc, &length);
        rc = text == NULL ? -1 : 0; /* GCOVR_EXCL_BR_LINE: alloc */
        if (rc == 0) {              /* GCOVR_EXCL_BR_LINE: alloc */
            result_string(out, text, length);
        }
    } else if (func_is(fn, "lang")) {
        int matched = node_lang(ctx, &args[0]);
        rc = matched < 0 ? -1 : 0; /* GCOVR_EXCL_BR_LINE: alloc */
        if (rc == 0) {             /* GCOVR_EXCL_BR_LINE: alloc */
            result_bool(out, matched);
        }
    } else if (func_is(fn, "id")) {
        rc = eval_id(ctx, &args[0], out);
    } else if (func_is(fn, "re:test")) {
        rc = exslt_re_test(ctx->tree, args, argc, out);
    } else if (func_is(fn, "re:replace")) {
        rc = exslt_re_replace(ctx->tree, args, out);
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
            } else {           /* GCOVR_EXCL_LINE: brace of the never-taken alloc-failure branch */
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
        } else {                             /* GCOVR_EXCL_LINE: brace of the never-taken alloc-failure branch */
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
        } else { /* GCOVR_EXCL_LINE: brace of the never-taken alloc-failure branch */
            rc = translate(text, sl, from, fl, to, tl, out);
        }
        PyMem_Free(text);
        PyMem_Free(from);
        PyMem_Free(to);
    } else if (ctx->extension != NULL &&
               (rc = ctx->extension(ctx->extension_ctx, ctx->node, fn->str, fn->str_len, args, argc, out)) != -2) {
        /* a registered extension handled it (rc is 0 or a propagated error) */
    } else {
        *ctx->feature = "this function";
        rc = -2;
    }
    for (int cleanup_index = 0; cleanup_index < argc; cleanup_index++) {
        xp_result_free(&args[cleanup_index]);
    }
    return rc;
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
