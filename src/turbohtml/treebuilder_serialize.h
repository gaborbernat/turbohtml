/* Tree serialization in the html5lib tree-construction "#document" format,
   #included into treebuilder.c (one translation unit, so the static helpers
   here still inline against the node tree). */

#include "entity_names.h"

/* ---------------------------------------------------------- serialization */

typedef struct {
    Py_UCS4 *data;
    Py_ssize_t len;
    Py_ssize_t cap;
    int failed;
} sbuf;

/* Grow the buffer so at least extra more code points fit, doubling so a run of
   appends stays amortized O(1). */
static void sbuf_reserve(sbuf *out, Py_ssize_t extra) {
    if (out->len + extra <= out->cap) {
        return;
    }
    Py_ssize_t cap = out->cap ? out->cap : 256;
    while (cap < out->len + extra) {
        cap *= 2;
    }
    Py_UCS4 *grown = PyMem_Realloc(out->data, (size_t)cap * sizeof(Py_UCS4));
    if (grown == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        out->failed = 1; /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
        return;          /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
    }
    out->data = grown;
    out->cap = cap;
}

static void sbuf_putc(sbuf *out, Py_UCS4 character) {
    sbuf_reserve(out, 1);
    if (out->failed) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return;        /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
    }
    out->data[out->len++] = character;
}

/* Append a run of code points in one bulk copy after a single capacity check. */
static void sbuf_put_run(sbuf *out, const Py_UCS4 *text, Py_ssize_t len) {
    sbuf_reserve(out, len);
    if (out->failed) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return;        /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
    }
    memcpy(out->data + out->len, text, (size_t)len * sizeof(Py_UCS4));
    out->len += len;
}

static void sbuf_puts(sbuf *out, const char *str) {
    Py_ssize_t len = (Py_ssize_t)strlen(str);
    sbuf_reserve(out, len);
    if (out->failed) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return;        /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
    }
    for (Py_ssize_t index = 0; index < len; index++) {
        out->data[out->len + index] = (Py_UCS4)(unsigned char)str[index];
    }
    out->len += len;
}

static void sbuf_put_ucs4(sbuf *out, const Py_UCS4 *text, Py_ssize_t len) {
    sbuf_put_run(out, text, len);
}

/* Write well-formed UTF-8 bytes (an interned attribute name) as code points. The
   common all-ASCII name is copied in bulk; only a name with a byte >= 0x80
   (a foreign mixed-case attribute) takes the per-code-point decoder. */
static void sbuf_put_utf8(sbuf *out, const char *bytes, Py_ssize_t len) {
    Py_ssize_t index = 0;
    while (index < len && (unsigned char)bytes[index] < 0x80) {
        index++;
    }
    if (index > 0) {
        sbuf_reserve(out, index);
        if (out->failed) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return;        /* GCOVR_EXCL_LINE: allocation-failure path */
        }
        for (Py_ssize_t ascii = 0; ascii < index; ascii++) {
            out->data[out->len + ascii] = (Py_UCS4)(unsigned char)bytes[ascii];
        }
        out->len += index;
    }
    while (index < len) {
        unsigned char lead = (unsigned char)bytes[index];
        Py_UCS4 character;
        if (lead < 0x80) {
            character = lead;
            index += 1;
        } else if (lead < 0xE0) {
            character = (Py_UCS4)(lead & 0x1F) << 6 | ((unsigned char)bytes[index + 1] & 0x3F);
            index += 2;
        } else if (lead < 0xF0) {
            character = (Py_UCS4)(lead & 0x0F) << 12 | ((unsigned char)(bytes[index + 1] & 0x3F)) << 6 |
                        ((unsigned char)bytes[index + 2] & 0x3F);
            index += 3;
        } else {
            character = (Py_UCS4)(lead & 0x07) << 18 | ((unsigned char)(bytes[index + 1] & 0x3F)) << 12 |
                        ((unsigned char)(bytes[index + 2] & 0x3F)) << 6 | ((unsigned char)bytes[index + 3] & 0x3F);
            index += 4;
        }
        sbuf_putc(out, character);
    }
}

/* Write an attribute's displayed name (the form the #document line uses) into buf:
   namespaced foreign attributes show "prefix localname", everything else is the
   stored name (foreign attribute case adjustments are applied at construction). */
static void render_attr_name(th_tree *tree, const th_node *node, const th_node_attr *attr, char *buf, size_t bufsize) {
    Py_ssize_t name_len;
    const char *name = th_attr_name(tree, attr->name_atom, &name_len);
    int to_space = node->ns != TH_NS_HTML && foreign_attr_namespaced(name, name_len);
    size_t write_index = 0;
    if (to_space && memchr(name, ':', (size_t)name_len) == NULL) {
        /* the only namespaced attribute without a prefix to split on is plain xmlns,
           which belongs to the xmlns namespace and renders as "xmlns xmlns"; the
           6-byte prefix always fits the 128-byte buffer, so no bound check is needed */
        memcpy(buf, "xmlns ", 6);
        write_index = 6;
    }
    for (const char *character = name; *character != '\0' && write_index + 1 < bufsize; character++) {
        buf[write_index++] = (to_space && *character == ':') ? ' ' : *character;
    }
    buf[write_index] = '\0';
}

/* The #document attribute sort works in fixed stack buffers: at most this many
   attributes are ordered, each rendered name capped at this many bytes. */
#define MAX_SORTED_ATTRS 64
#define MAX_ATTR_NAME 128

/* Emit one node's #document line (and, for an element, its sorted attribute
   lines). The children are walked by serialize_node, so this never recurses. */
static void serialize_node_line(sbuf *out, th_tree *tree, th_node *node, int depth) {
    if (node->type == TH_NODE_TEXT) {
        need_text(tree, node); /* realize a zero-copy span before output */
    }
    /* html5lib format: "| " then two spaces per depth level, then the node */
    sbuf_puts(out, "| ");
    for (int index = 0; index < depth; index++) {
        sbuf_puts(out, "  ");
    }
    switch (node->type) { /* GCOVR_EXCL_BR_LINE: th_node_type is exhaustive; the implicit default is unreachable */
    case TH_NODE_DOCTYPE:
        sbuf_puts(out, "<!DOCTYPE ");
        sbuf_put_ucs4(out, node->text, node->text_len);
        sbuf_putc(out, '>');
        break;
    case TH_NODE_COMMENT:
        sbuf_puts(out, "<!-- ");
        sbuf_put_ucs4(out, node->text, node->text_len);
        sbuf_puts(out, " -->");
        break;
    case TH_NODE_TEXT:
        sbuf_putc(out, '"');
        sbuf_put_ucs4(out, node->text, node->text_len);
        sbuf_putc(out, '"');
        break;
    case TH_NODE_ELEMENT:
        sbuf_putc(out, '<');
        if (node->ns == TH_NS_SVG) {
            sbuf_puts(out, "svg ");
        } else if (node->ns == TH_NS_MATHML) {
            sbuf_puts(out, "math ");
        }
        sbuf_put_ucs4(out, node->text, node->text_len);
        sbuf_putc(out, '>');
        break;
    case TH_NODE_CONTENT:
        sbuf_puts(out, "content");
        break;
    /* GCOVR_EXCL_START: a WHATWG-conformant parse never yields a PI (folded to a
       comment) or a CDATA section (folded to text), so the #document dumper, which
       only serves parsed trees, never reaches these. */
    case TH_NODE_PI:
        sbuf_puts(out, "<?");
        sbuf_put_ucs4(out, node->text, node->text_len);
        sbuf_putc(out, '>');
        break;
    case TH_NODE_CDATA:
        sbuf_puts(out, "<![CDATA[");
        sbuf_put_ucs4(out, node->text, node->text_len);
        sbuf_puts(out, "]]>");
        break;
        /* GCOVR_EXCL_STOP */
    case TH_NODE_DOCUMENT: /* GCOVR_EXCL_LINE: the document node is the serialization root, never a line itself */
        break;             /* GCOVR_EXCL_LINE: same — the document node is never reached as a child */
    }
    sbuf_putc(out, '\n');
    /* attributes: each on its own deeper line, output in lexicographic name
       order (the html5lib #document format sorts them). Only elements have
       attributes; a text node's attr_count field holds a span offset. */
    Py_ssize_t order[MAX_SORTED_ATTRS];
    Py_ssize_t count =
        node->type == TH_NODE_ELEMENT ? (node->attr_count < MAX_SORTED_ATTRS ? node->attr_count : MAX_SORTED_ATTRS) : 0;
    for (Py_ssize_t index = 0; index < count; index++) {
        order[index] = index;
    }
    /* Sort on the displayed name so a namespaced attribute (shown as
       "prefix localname") orders by its space, which precedes a literal colon. */
    char ke_buf[MAX_ATTR_NAME];
    char cmp_buf[MAX_ATTR_NAME];
    for (Py_ssize_t index = 1; index < count; index++) { /* insertion sort; attribute counts are tiny */
        Py_ssize_t key = order[index];
        render_attr_name(tree, node, &node->attrs[key], ke_buf, sizeof(ke_buf));
        Py_ssize_t prev = index - 1;
        while (prev >= 0 && (render_attr_name(tree, node, &node->attrs[order[prev]], cmp_buf, sizeof(cmp_buf)),
                             strcmp(cmp_buf, ke_buf) > 0)) {
            order[prev + 1] = order[prev];
            prev--;
        }
        order[prev + 1] = key;
    }
    for (Py_ssize_t index = 0; index < count; index++) {
        th_node_attr *attr = &node->attrs[order[index]];
        sbuf_puts(out, "| ");
        for (int level = 0; level <= depth; level++) {
            sbuf_puts(out, "  ");
        }
        /* xlink:/xml:/xmlns: serialize with a space; the mixed-case spelling of an
           SVG/MathML attribute is already stored, applied at construction */
        Py_ssize_t name_len;
        const char *name = th_attr_name(tree, attr->name_atom, &name_len);
        if (node->ns != TH_NS_HTML && foreign_attr_namespaced(name, name_len)) {
            if (memchr(name, ':', (size_t)name_len) == NULL) {
                sbuf_puts(out, "xmlns "); /* plain xmlns (no prefix to split on) renders with its namespace prefix */
            }
            for (const char *character = name; *character; character++) {
                sbuf_putc(out, *character == ':' ? (Py_UCS4)' ' : (Py_UCS4)*character);
            }
        } else {
            sbuf_put_utf8(out, name, name_len);
        }
        sbuf_puts(out, "=\"");
        sbuf_put_ucs4(out, attr->value, attr->value_len);
        sbuf_putc(out, '"');
        sbuf_putc(out, '\n');
    }
}

/* Dump node and its subtree in the html5lib #document format. The walk is
   iterative (descend through first_child, ascend through parent) so an
   arbitrarily deep tree never overflows the C stack. */
static void serialize_node(sbuf *out, th_tree *tree, th_node *root, int depth0) {
    th_node *node = root;
    int depth = depth0;
    while (1) {
        serialize_node_line(out, tree, node, depth);
        if (node->first_child != NULL) {
            node = node->first_child;
            depth += 1;
            continue;
        }
        while (node != root && node->next_sibling == NULL) {
            node = node->parent;
            depth -= 1;
        }
        if (node == root) {
            break;
        }
        node = node->next_sibling;
    }
}

Py_UCS4 *th_tree_serialize(th_tree *tree, Py_ssize_t *out_len) {
    sbuf out = {NULL, 0, 0, 0};
    /* a fragment serializes the context root's children; a document serializes
       the document node's children */
    th_node *top = tree->fragment_root != NULL ? tree->fragment_root : tree->document;
    for (th_node *child = top->first_child; child != NULL; child = child->next_sibling) {
        serialize_node(&out, tree, child, 0);
    }
    if (out.failed) {         /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        PyMem_Free(out.data); /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
        return NULL;          /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
    }
    *out_len = out.len;
    if (out.data == NULL) {
        /* an empty tree (whitespace-only input) serializes to nothing; hand
           back a real zero-length allocation so NULL stays unambiguously the
           failure signal for the caller */
        out.data = PyMem_Malloc(1);
        if (out.data == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return NULL;        /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
        }
    }
    return out.data;
}

/* --------------------------------------------- navigable-tree HTML output */

/* The escape policy serialize()/encode() expose through the Formatter enum. */
enum th_formatter {
    TH_FMT_WHATWG,  /* conformant minimal escaping: & < > nbsp in text, & " nbsp in attrs */
    TH_FMT_MINIMAL, /* the three structural characters only, in both contexts */
    TH_FMT_NAMED,   /* HTML named entities for every character that has one */
};

/* Whether a character has a named reference under the NAMED formatter. The ASCII
   ones are exactly & " < >, so the generated table is only consulted past 0x7F. */
static int sbuf_named_special(Py_UCS4 character) {
    if (character < 0x80) {
        return character == '&' || character == '"' || character == '<' || character == '>';
    }
    return th_entity_name(character) != NULL;
}

/* The WHATWG/MINIMAL special set tested over a 64-bit word of two UCS-4 code
   points: & always, < > when angle brackets escape (text, or any MINIMAL), " in
   a WHATWG attribute value, and the no-break space WHATWG folds. Each probe sets
   the matching lane's high bit; a nonzero result means a special is in the pair. */
static inline uint64_t sbuf_special_mask(uint64_t word, int escape_angle, int escape_quote, int escape_nbsp) {
    uint64_t mask = swar_haslane32(word, '&');
    if (escape_angle) {
        mask |= swar_haslane32(word, '<') | swar_haslane32(word, '>');
    }
    if (escape_quote) {
        mask |= swar_haslane32(word, '"');
    }
    if (escape_nbsp) {
        mask |= swar_haslane32(word, 0xA0);
    }
    return mask;
}

/* Emit the replacement for a flagged character. */
static void sbuf_put_special(sbuf *out, Py_UCS4 character, int formatter) {
    const char *name = formatter == TH_FMT_NAMED ? th_entity_name(character) : NULL;
    if (name != NULL) {
        sbuf_putc(out, '&');
        sbuf_puts(out, name);
        sbuf_putc(out, ';');
    } else if (character == '&') {
        sbuf_puts(out, "&amp;");
    } else if (character == '<') {
        sbuf_puts(out, "&lt;");
    } else if (character == '>') {
        sbuf_puts(out, "&gt;");
    } else if (character == '"') {
        sbuf_puts(out, "&quot;");
    } else {
        sbuf_puts(out, "&nbsp;"); /* the only remaining flagged character is U+00A0 */
    }
}

/* Append NAMED-formatter text: bulk-copy each run with no named reference and
   rewrite the rest. NAMED consults a table past 0x7F, so it stays scalar. */
static void sbuf_put_named_text(sbuf *out, const Py_UCS4 *text, Py_ssize_t len) {
    Py_ssize_t index = 0;
    while (index < len) {
        Py_ssize_t start = index;
        while (index < len && !sbuf_named_special(text[index])) {
            index++;
        }
        if (index > start) {
            sbuf_put_run(out, &text[start], index - start);
        }
        if (index < len) {
            sbuf_put_special(out, text[index], TH_FMT_NAMED);
            index++;
        }
    }
}

/* Append text under the WHATWG or MINIMAL formatter, bulk-copying each run with
   nothing to escape and rewriting only the specials between. The tree stores
   text as UCS-4, so the clean-run scan tests two code points per 64-bit word
   with the same SWAR lane probes escape.c uses, hopping over the long unescaped
   spans real documents are made of instead of classifying every character. When
   a pair holds a special, its exact code point is recovered from the lane mask
   over a word built low-lane-first, so the position is independent of byte order
   and of which character class matched. */
static void sbuf_put_text(sbuf *out, const Py_UCS4 *text, Py_ssize_t len, int in_attr, int formatter) {
    if (formatter == TH_FMT_NAMED) {
        sbuf_put_named_text(out, text, len);
        return;
    }
    int escape_angle = formatter == TH_FMT_MINIMAL || !in_attr;
    int escape_quote = in_attr && formatter == TH_FMT_WHATWG;
    int escape_nbsp = formatter == TH_FMT_WHATWG;
    Py_ssize_t index = 0;
    while (index < len) {
        Py_ssize_t start = index;
        Py_ssize_t special = -1;
        while (index + UCS4_LANES <= len) {
            uint64_t word;
            memcpy(&word, &text[index], sizeof(word));
            if (sbuf_special_mask(word, escape_angle, escape_quote, escape_nbsp) != 0) {
                uint64_t ordered = (uint64_t)text[index] | ((uint64_t)text[index + 1] << 32);
                uint64_t omask = sbuf_special_mask(ordered, escape_angle, escape_quote, escape_nbsp);
                special = index + (Py_ssize_t)((omask & 0x80000000ULL) == 0);
                break;
            }
            index += UCS4_LANES;
        }
        if (special < 0 && index < len) {
            /* one code point trails the last full pair; pad with a non-special
               lane so the same mask probe classifies it without a buffer overread */
            uint64_t word = (uint64_t)text[index];
            if (sbuf_special_mask(word, escape_angle, escape_quote, escape_nbsp) != 0) {
                special = index;
            }
        }
        Py_ssize_t stop = special < 0 ? len : special;
        if (stop > start) {
            sbuf_put_run(out, &text[start], stop - start);
        }
        if (special < 0) {
            break;
        }
        sbuf_put_special(out, text[special], formatter);
        index = special + 1;
    }
}

/* An element whose text children serialize literally rather than escaped: the
   WHATWG literal set is style/script/xmp/iframe/noembed/noframes/plaintext.
   noscript carries the rawtext flag for tokenization but, since this parser runs
   with scripting disabled, its content is normal escaped markup. */
static int is_rawtext_element(const th_node *node) {
    /* the caller passes only element nodes, so this skips the node-type check */
    if (node->ns != TH_NS_HTML) {
        return 0; /* foreign elements (svg, mathml) never carry html raw-text content */
    }
    if (node->atom == TH_TAG_SCRIPT || node->atom == TH_TAG_PLAINTEXT) {
        return 1;
    }
    /* noscript is raw-text only with scripting on; this parser runs scripting-disabled, so it escapes */
    return (node->tag_flags & TH_TAG_RAWTEXT) && node->atom != TH_TAG_NOSCRIPT;
}

/* The WHATWG fragment-serialization void set extends the parser's void elements
   with `frame`: it is emitted as a start tag only, never an end tag. `frame` is
   absent from is_void_atom because, unlike a true void element, it is a normal
   open element during parsing (in frameset mode it is inserted childless), so
   widening is_void_atom would wrongly make a stray in-body <frame> swallow no
   following content. */
static int is_serialize_void_atom(uint16_t atom) {
    return atom == TH_TAG_FRAME || is_void_atom(atom);
}

/* The doctype name length: build_doctype_text stores "name" optionally followed
   by ` "public" "system"`, but HTML serialization emits only the name. */
static Py_ssize_t doctype_name_len(const th_node *node) {
    Py_ssize_t index = 0;
    while (index < node->text_len && node->text[index] != ' ') {
        index++;
    }
    return index;
}

/* A pre/textarea/listing element whose first child is a text node beginning with
   a newline needs an extra leading newline on output: the parser drops one such
   newline when reading, so re-emitting it keeps the round trip faithful. */
static int ser_needs_leading_newline(th_tree *tree, th_node *node) {
    if (node->ns != TH_NS_HTML) {
        return 0;
    }
    if (node->atom != TH_TAG_PRE && node->atom != TH_TAG_TEXTAREA && node->atom != TH_TAG_LISTING) {
        return 0;
    }
    /* a text node always carries at least one code point (the builder never
       inserts an empty one), so reading the first character here is safe */
    th_node *first = node->first_child;
    return first != NULL && first->type == TH_NODE_TEXT && need_text(tree, first)[0] == '\n';
}

/* ASCII case-insensitive compare of a UCS-4 attribute value against a lowercase
   literal: the value matches when it has the same length and folds to the same
   bytes (only A-Z fold, the only case mapping the labels here need). */
static int ser_value_iequals(const Py_UCS4 *value, Py_ssize_t len, const char *ascii) {
    Py_ssize_t index = 0;
    for (; index < len && ascii[index] != '\0'; index++) {
        Py_UCS4 character = value[index];
        if (character >= 'A' && character <= 'Z') {
            character += 'a' - 'A';
        }
        if (character != (Py_UCS4)(unsigned char)ascii[index]) {
            return 0;
        }
    }
    return index == len && ascii[index] == '\0';
}

/* How a <meta> element declares the document encoding, for the meta_charset
   normalizer: 1 a `charset` attribute, 2 an http-equiv="content-type" with a
   `content` attribute, 0 neither (or not an HTML <meta>). */
static int ser_meta_charset_kind(th_tree *tree, const th_node *node) {
    if (node->ns != TH_NS_HTML || node->atom != TH_TAG_META) {
        return 0;
    }
    if (th_node_attr_find(tree, (th_node *)node, "charset", 7) >= 0) {
        return 1;
    }
    Py_ssize_t equiv = th_node_attr_find(tree, (th_node *)node, "http-equiv", 10);
    if (equiv >= 0 && th_node_attr_find(tree, (th_node *)node, "content", 7) >= 0 &&
        ser_value_iequals(node->attrs[equiv].value, node->attrs[equiv].value_len, "content-type")) {
        return 2;
    }
    return 0;
}

/* Whether head already declares a charset through a direct <meta> child, so the
   meta_charset option normalizes that one in place instead of injecting another. */
static int ser_head_has_charset_meta(th_tree *tree, const th_node *head) {
    for (th_node *child = head->first_child; child != NULL; child = child->next_sibling) {
        if (child->type == TH_NODE_ELEMENT && ser_meta_charset_kind(tree, child) != 0) {
            return 1;
        }
    }
    return 0;
}

/* Emit a fresh charset declaration, <meta charset="LABEL">. */
static void ser_emit_meta_charset(sbuf *out, const th_serialize_opts *opts) {
    sbuf_puts(out, "<meta charset=\"");
    sbuf_put_utf8(out, opts->charset, opts->charset_len);
    sbuf_puts(out, "\">");
}

/* Lexicographic compare of two interned attribute names by bytes, the shorter
   name ordering first on a shared prefix (the html5lib alphabetical-attributes
   order over the stored, parser-lowercased name). */
static int ser_name_cmp(const char *left, Py_ssize_t left_len, const char *right, Py_ssize_t right_len) {
    Py_ssize_t min_len = left_len < right_len ? left_len : right_len;
    int order = memcmp(left, right, (size_t)min_len);
    if (order != 0) {
        return order;
    }
    return left_len < right_len ? -1 : left_len > right_len;
}

/* Insertion-sort order[0..count) into ascending attribute-name order. Counts are
   tiny, so the quadratic sort beats any setup an asymptotically faster one needs. */
static void ser_sort_order(th_tree *tree, const th_node *node, Py_ssize_t *order, Py_ssize_t count) {
    for (Py_ssize_t index = 0; index < count; index++) {
        order[index] = index;
    }
    for (Py_ssize_t index = 1; index < count; index++) {
        Py_ssize_t key = order[index];
        Py_ssize_t key_len;
        const char *key_name = th_attr_name(tree, node->attrs[key].name_atom, &key_len);
        Py_ssize_t prev = index - 1;
        while (prev >= 0) {
            Py_ssize_t prev_len;
            const char *prev_name = th_attr_name(tree, node->attrs[order[prev]].name_atom, &prev_len);
            if (ser_name_cmp(prev_name, prev_len, key_name, key_len) <= 0) {
                break;
            }
            order[prev + 1] = order[prev];
            prev--;
        }
        order[prev + 1] = key;
    }
}

/* The order to emit node's attributes in: NULL means source order (sorting off, or
   fewer than two attributes), otherwise a filled index array — the caller's stack
   buffer for up to MAX_SORTED_ATTRS attributes, else a heap block freed through
   ser_attr_order_free. */
static Py_ssize_t *ser_attr_order(th_tree *tree, const th_node *node, int sort, Py_ssize_t *stack) {
    if (!sort || node->attr_count < 2) {
        return NULL;
    }
    Py_ssize_t *order =
        node->attr_count <= MAX_SORTED_ATTRS ? stack : PyMem_Malloc((size_t)node->attr_count * sizeof(Py_ssize_t));
    if (order == NULL) { /* GCOVR_EXCL_BR_LINE: only the heap path can fail, and OOM is unforceable */
        return NULL;     /* GCOVR_EXCL_LINE: degrade to source order on allocation failure */
    }
    ser_sort_order(tree, node, order, node->attr_count);
    return order;
}

static void ser_attr_order_free(Py_ssize_t *order, const Py_ssize_t *stack) {
    if (order != NULL && order != stack) {
        PyMem_Free(order);
    }
}

/* Under meta_charset, rewrite a charset meta's declaration to the target label:
   charset="LABEL" (kind 1) or content="text/html; charset=LABEL" (kind 2). Returns
   1 when it emitted the attribute, 0 when the caller should emit the stored value.
   The element is an HTML <meta>, whose attribute names the parser has lowercased,
   so a byte compare against the lowercase spelling is exact. */
static int ser_put_charset_value(sbuf *out, const th_serialize_opts *opts, int kind, const char *name,
                                 Py_ssize_t name_len) {
    if (kind == 1 && name_len == 7 && memcmp(name, "charset", 7) == 0) {
        sbuf_puts(out, "=\"");
        sbuf_put_utf8(out, opts->charset, opts->charset_len);
        sbuf_putc(out, '"');
        return 1;
    }
    if (kind == 2 && name_len == 7 && memcmp(name, "content", 7) == 0) {
        sbuf_puts(out, "=\"text/html; charset=");
        sbuf_put_utf8(out, opts->charset, opts->charset_len);
        sbuf_putc(out, '"');
        return 1;
    }
    return 0;
}

/* When meta_charset is on and node is a <head> that declares no charset of its own,
   emit the <meta charset> as its first child so the output names the encoding. The
   atom guard means this is a no-op for every element but the document head. */
static void ser_inject_head_meta(sbuf *out, th_tree *tree, const th_node *node, const th_serialize_opts *opts) {
    if (opts->inject_meta && node->ns == TH_NS_HTML && node->atom == TH_TAG_HEAD &&
        !ser_head_has_charset_meta(tree, node)) {
        ser_emit_meta_charset(out, opts);
    }
}

/* Write an element's start tag, "<tag attrs...>": attributes in source order, or in
   name order when opts asks; values double-quoted and escaped under the formatter,
   with a charset meta's declaration normalized when meta_charset is on. */
static void ser_open_tag(sbuf *out, th_tree *tree, th_node *node, const th_serialize_opts *opts) {
    sbuf_putc(out, '<');
    sbuf_put_ucs4(out, node->text, node->text_len);
    Py_ssize_t stack_order[MAX_SORTED_ATTRS];
    Py_ssize_t *order = ser_attr_order(tree, node, opts->sort_attributes, stack_order);
    int charset_kind = opts->inject_meta ? ser_meta_charset_kind(tree, node) : 0;
    for (Py_ssize_t position = 0; position < node->attr_count; position++) {
        th_node_attr *attr = &node->attrs[order != NULL ? order[position] : position];
        sbuf_putc(out, ' ');
        Py_ssize_t name_len;
        const char *name = th_attr_name(tree, attr->name_atom, &name_len);
        sbuf_put_utf8(out, name, name_len);
        if (ser_put_charset_value(out, opts, charset_kind, name, name_len)) {
            continue;
        }
        sbuf_puts(out, "=\"");
        sbuf_put_text(out, attr->value, attr->value_len, 1, opts->formatter);
        sbuf_putc(out, '"');
    }
    ser_attr_order_free(order, stack_order);
    sbuf_putc(out, '>');
}

static void ser_close_tag(sbuf *out, th_node *node) {
    sbuf_puts(out, "</");
    sbuf_put_ucs4(out, node->text, node->text_len);
    sbuf_putc(out, '>');
}

/* Outer serialization with no inserted whitespace (the WHATWG fragment
   algorithm), parameterized by the escape formatter. The walk is iterative,
   descending through first_child and ascending through parent pointers, so a
   tree of any depth serializes without recursing one C stack frame per level. */
static void serialize_compact(sbuf *out, th_tree *tree, th_node *root, const th_serialize_opts *opts) {
    th_node *node = root;
    while (1) {
        th_node *descend = NULL;
        switch (node->type) { /* GCOVR_EXCL_BR_LINE: th_node_type is exhaustive; the implicit default is unreachable */
        case TH_NODE_ELEMENT:
            ser_open_tag(out, tree, node, opts);
            ser_inject_head_meta(out, tree, node, opts);
            if (node->ns == TH_NS_HTML && is_serialize_void_atom(node->atom)) {
                break; /* void elements have no children or end tag */
            }
            if (ser_needs_leading_newline(tree, node)) {
                sbuf_putc(out, '\n');
            }
            if (is_rawtext_element(node)) {
                /* a rawtext element's children are always text nodes */
                for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
                    sbuf_put_ucs4(out, need_text(tree, child), child->text_len);
                }
                ser_close_tag(out, node);
                break;
            }
            if (node->first_child != NULL) {
                descend = node->first_child;
            } else {
                ser_close_tag(out, node); /* an empty element still takes an end tag */
            }
            break;
        case TH_NODE_TEXT:
            sbuf_put_text(out, need_text(tree, node), node->text_len, 0, opts->formatter);
            break;
        case TH_NODE_COMMENT:
            sbuf_puts(out, "<!--");
            sbuf_put_ucs4(out, node->text, node->text_len);
            sbuf_puts(out, "-->");
            break;
        case TH_NODE_DOCTYPE:
            sbuf_puts(out, "<!DOCTYPE ");
            sbuf_put_ucs4(out, node->text, doctype_name_len(node));
            sbuf_putc(out, '>');
            break;
        case TH_NODE_PI:
            sbuf_puts(out, "<?");
            sbuf_put_ucs4(out, node->text, node->text_len);
            sbuf_putc(out, '>');
            break;
        case TH_NODE_CDATA:
            sbuf_puts(out, "<![CDATA[");
            sbuf_put_ucs4(out, node->text, node->text_len);
            sbuf_puts(out, "]]>");
            break;
        case TH_NODE_CONTENT:
        case TH_NODE_DOCUMENT:
            descend = node->first_child; /* a transparent container emits only its children */
            break;
        }
        if (descend != NULL) {
            node = descend;
            continue;
        }
        /* ascend toward the root, closing each element whose children are done */
        while (node != root) {
            if (node->next_sibling != NULL) {
                node = node->next_sibling;
                break;
            }
            node = node->parent;
            if (node->type == TH_NODE_ELEMENT) {
                ser_close_tag(out, node);
            }
        }
        if (node == root) {
            break;
        }
    }
}

/* Indentation context for the pretty form: the output options plus the per-level
   unit the layout's Indent supplies. */
typedef struct {
    const th_serialize_opts *out;
    const Py_UCS4 *indent;
    Py_ssize_t indent_len;
} ser_opts;

static void ser_newline_indent(sbuf *out, const ser_opts *opts, int depth) {
    sbuf_putc(out, '\n');
    for (int level = 0; level < depth; level++) {
        sbuf_put_ucs4(out, opts->indent, opts->indent_len);
    }
}

/* Pretty serialization: write node at the current position with no leading
   whitespace; a parent emits the newline and indent before each child, so the
   root starts at column zero. Raw-text and whitespace-significant elements
   (script/style/pre/textarea/listing) keep their content verbatim, since
   reflowing it would change meaning. */
static void serialize_pretty(sbuf *out, th_tree *tree, th_node *root, const ser_opts *opts, int depth0) {
    th_node *node = root;
    int depth = depth0;
    while (1) {
        th_node *descend = NULL;
        switch (node->type) { /* GCOVR_EXCL_BR_LINE: th_node_type is exhaustive; the implicit default is unreachable */
        case TH_NODE_ELEMENT: {
            ser_open_tag(out, tree, node, opts->out);
            if (node->ns == TH_NS_HTML && is_serialize_void_atom(node->atom)) {
                break;
            }
            int raw = is_rawtext_element(node);
            int preserve = raw || ser_needs_leading_newline(tree, node) ||
                           (node->ns == TH_NS_HTML && (node->atom == TH_TAG_PRE || node->atom == TH_TAG_TEXTAREA ||
                                                       node->atom == TH_TAG_LISTING));
            if (preserve) {
                /* a whitespace-significant element keeps its content verbatim: its
                   children serialize compactly (itself iterative), so the pretty
                   walk treats it as a leaf and never recurses through it */
                if (ser_needs_leading_newline(tree, node)) {
                    sbuf_putc(out, '\n');
                }
                for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
                    if (raw && child->type == TH_NODE_TEXT) { /* GCOVR_EXCL_BR_LINE */
                        sbuf_put_ucs4(out, need_text(tree, child), child->text_len);
                    } else {
                        serialize_compact(out, tree, child, opts->out);
                    }
                }
                ser_close_tag(out, node);
                break;
            }
            /* meta_charset injects the declaration as head's first child, on its own
               indented line (head is never a preserve/raw element, so this is reached) */
            int inject = opts->out->inject_meta && node->ns == TH_NS_HTML && node->atom == TH_TAG_HEAD &&
                         !ser_head_has_charset_meta(tree, node);
            if (node->first_child == NULL && !inject) {
                ser_close_tag(out, node);
                break;
            }
            if (inject) {
                ser_newline_indent(out, opts, depth + 1);
                ser_emit_meta_charset(out, opts->out);
            }
            if (node->first_child == NULL) {
                ser_newline_indent(out, opts, depth);
                ser_close_tag(out, node);
                break;
            }
            ser_newline_indent(out, opts, depth + 1);
            descend = node->first_child;
            break;
        }
        case TH_NODE_TEXT:
            sbuf_put_text(out, need_text(tree, node), node->text_len, 0, opts->out->formatter);
            break;
        case TH_NODE_COMMENT:
            sbuf_puts(out, "<!--");
            sbuf_put_ucs4(out, node->text, node->text_len);
            sbuf_puts(out, "-->");
            break;
        case TH_NODE_DOCTYPE:
            sbuf_puts(out, "<!DOCTYPE ");
            sbuf_put_ucs4(out, node->text, doctype_name_len(node));
            sbuf_putc(out, '>');
            break;
        case TH_NODE_PI:
            sbuf_puts(out, "<?");
            sbuf_put_ucs4(out, node->text, node->text_len);
            sbuf_putc(out, '>');
            break;
        case TH_NODE_CDATA:
            sbuf_puts(out, "<![CDATA[");
            sbuf_put_ucs4(out, node->text, node->text_len);
            sbuf_puts(out, "]]>");
            break;
        case TH_NODE_CONTENT:
        case TH_NODE_DOCUMENT:
            /* a transparent container lays its children out at its own depth */
            descend = node->first_child;
            break;
        }
        if (descend != NULL) {
            if (node->type == TH_NODE_ELEMENT) {
                depth += 1; /* an element indents its children one level deeper */
            }
            node = descend;
            continue;
        }
        /* ascend toward the root, closing each element once its children are done */
        while (node != root) {
            if (node->next_sibling != NULL) {
                ser_newline_indent(out, opts, depth);
                node = node->next_sibling;
                break;
            }
            th_node *parent = node->parent;
            if (parent->type == TH_NODE_ELEMENT) {
                depth -= 1;
                ser_newline_indent(out, opts, depth);
                ser_close_tag(out, parent);
            }
            node = parent;
        }
        if (node == root) {
            break;
        }
    }
}

/* Hand a filled sbuf back to the caller, normalizing an empty result to a real
   zero-length allocation so NULL unambiguously means failure. */
static Py_UCS4 *sbuf_finish(sbuf *out, Py_ssize_t *out_len) {
    if (out->failed) {         /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        PyMem_Free(out->data); /* GCOVR_EXCL_LINE: allocation-failure path */
        return NULL;           /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    *out_len = out->len;
    if (out->data == NULL) {
        out->data = PyMem_Malloc(1); /* GCOVR_EXCL_BR_LINE: empty output, allocation cannot be forced to fail */
    }
    return out->data;
}

th_node *th_tree_document(th_tree *tree) {
    return tree->fragment_root != NULL ? tree->fragment_root : tree->document;
}

Py_UCS4 *th_node_data(th_tree *tree, th_node *node, Py_ssize_t *out_len) {
    Py_ssize_t len = node->type == TH_NODE_DOCTYPE ? doctype_name_len(node) : node->text_len;
    *out_len = len;
    Py_UCS4 *out = PyMem_Malloc((len ? len : 1) * sizeof(Py_UCS4));
    if (out == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;   /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    if (len) {
        memcpy(out, need_text(tree, node), (size_t)len * sizeof(Py_UCS4));
    }
    return out;
}

/* The doctype's public and system identifiers, parsed out of the stored
   "name \"public\" \"system\"" text into slices of the node's own text. Returns 1
   and sets all four out params when the doctype carries identifiers, 0 when it is
   just a name. Either identifier may be present but empty (a SYSTEM doctype has no
   public id, a PUBLIC doctype may omit the system id), and build_doctype_text
   always writes both quoted strings together, so the closing quotes are
   guaranteed and no bounds check is needed. */
int th_node_doctype_ids(th_node *node, const Py_UCS4 **public_id, Py_ssize_t *public_len, const Py_UCS4 **system_id,
                        Py_ssize_t *system_len) {
    Py_ssize_t name_len = doctype_name_len(node);
    if (name_len >= node->text_len) {
        return 0;
    }
    Py_ssize_t pos = name_len + 2; /* skip the space and the opening quote */
    *public_id = &node->text[pos];
    while (node->text[pos] != '"') {
        pos++;
    }
    *public_len = &node->text[pos] - *public_id;
    pos += 3; /* skip the closing quote, the separating space, and the next opening quote */
    *system_id = &node->text[pos];
    while (node->text[pos] != '"') {
        pos++;
    }
    *system_len = &node->text[pos] - *system_id;
    return 1;
}

static void collect_text(sbuf *out, th_tree *tree, th_node *node) {
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        if (child->type == TH_NODE_TEXT) {
            sbuf_put_ucs4(out, need_text(tree, child), child->text_len);
        } else if (child->type == TH_NODE_ELEMENT || child->type == TH_NODE_CONTENT) {
            collect_text(out, tree, child);
        }
    }
}

Py_UCS4 *th_node_text(th_tree *tree, th_node *node, Py_ssize_t *out_len) {
    sbuf out = {NULL, 0, 0, 0};
    if (node->type == TH_NODE_TEXT) {
        sbuf_put_ucs4(&out, need_text(tree, node), node->text_len);
    } else {
        collect_text(&out, tree, node);
    }
    return sbuf_finish(&out, out_len);
}

/* When serializing a whole parsed document, the output length tracks the input
   length closely, so reserve it up front. That turns the buffer's geometric
   doubling (about ten reallocs and ~2x the output in memmoves for a 235 kB page)
   into a single allocation. A subtree serialize keeps the default growth, since
   the input length would wildly over-reserve. */
static void sbuf_presize_for_root(sbuf *out, th_tree *tree, th_node *node) {
    if (node == th_tree_document(tree)) {
        /* reserving the input length is a no-op for an empty or programmatic
           tree (length 0), so no separate guard is needed */
        sbuf_reserve(out, tree->length);
    }
}

/* The WHATWG-conformant defaults the html/inner_html accessors serialize under:
   minimal escaping, source attribute order, no charset injection. */
static const th_serialize_opts ser_default_opts = {TH_FMT_WHATWG, 0, 0, NULL, 0};

Py_UCS4 *th_node_html(th_tree *tree, th_node *node, Py_ssize_t *out_len) {
    sbuf out = {NULL, 0, 0, 0};
    sbuf_presize_for_root(&out, tree, node);
    serialize_compact(&out, tree, node, &ser_default_opts);
    return sbuf_finish(&out, out_len);
}

Py_UCS4 *th_node_inner_html(th_tree *tree, th_node *node, Py_ssize_t *out_len) {
    sbuf out = {NULL, 0, 0, 0};
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        serialize_compact(&out, tree, child, &ser_default_opts);
    }
    return sbuf_finish(&out, out_len);
}

Py_UCS4 *th_node_serialize(th_tree *tree, th_node *node, const th_serialize_opts *opts, const Py_UCS4 *indent,
                           Py_ssize_t indent_len, Py_ssize_t *out_len) {
    sbuf out = {NULL, 0, 0, 0};
    sbuf_presize_for_root(&out, tree, node);
    if (indent == NULL) {
        serialize_compact(&out, tree, node, opts);
    } else {
        ser_opts pretty = {opts, indent, indent_len};
        serialize_pretty(&out, tree, node, &pretty, 0);
    }
    return sbuf_finish(&out, out_len);
}
