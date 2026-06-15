/* Tree serialization in the html5lib tree-construction "#document" format,
   #included into treebuilder.c (one translation unit, so the static helpers
   here still inline against the node tree). */

/* ---------------------------------------------------------- serialization */

typedef struct {
    Py_UCS4 *data;
    Py_ssize_t len;
    Py_ssize_t cap;
    int failed;
} sbuf;

static void sbuf_putc(sbuf *out, Py_UCS4 character) {
    if (out->len == out->cap) {
        Py_ssize_t cap = out->cap ? out->cap * 2 : 256;
        Py_UCS4 *grown = PyMem_Realloc(out->data, (size_t)cap * sizeof(Py_UCS4));
        if (grown == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            out->failed = 1; /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
            return;          /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
        }
        out->data = grown;
        out->cap = cap;
    }
    out->data[out->len++] = character;
}

static void sbuf_puts(sbuf *out, const char *str) {
    for (; *str; str++) {
        sbuf_putc(out, (Py_UCS4)*str);
    }
}

static void sbuf_put_ucs4(sbuf *out, const Py_UCS4 *text, Py_ssize_t len) {
    for (Py_ssize_t index = 0; index < len; index++) {
        sbuf_putc(out, text[index]);
    }
}

/* Write well-formed UTF-8 bytes (an interned attribute name) as code points. */
static void sbuf_put_utf8(sbuf *out, const char *bytes, Py_ssize_t len) {
    Py_ssize_t index = 0;
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

/* Write an attribute's displayed name (the form the #document line uses) into
   buf: namespaced foreign attributes show "prefix localname", SVG attributes
   take their mixed-case spelling, everything else is the lowercased name. */
static void render_attr_name(th_tree *tree, const th_node *node, const th_node_attr *attr, char *buf, size_t bufsize) {
    Py_ssize_t name_len;
    const char *name = th_attr_name(tree, attr->name_atom, &name_len);
    const char *mixed = node->ns != TH_NS_HTML ? foreign_adjust_attr(name, name_len, node->ns) : NULL;
    const char *src = name;
    int to_space = 0;
    if (node->ns != TH_NS_HTML && foreign_attr_namespaced(name, name_len)) {
        to_space = 1;
    } else if (mixed != NULL) {
        src = mixed;
    }
    size_t write_index = 0;
    for (const char *character = src; *character != '\0' && write_index + 1 < bufsize; character++) {
        buf[write_index++] = (to_space && *character == ':') ? ' ' : *character;
    }
    buf[write_index] = '\0';
}

static void serialize_node(sbuf *out, th_tree *tree, th_node *node, int depth) {
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
    case TH_NODE_DOCUMENT: /* GCOVR_EXCL_LINE: the document node is the serialization root, never a line itself */
        break;             /* GCOVR_EXCL_LINE: same — the document node is never reached as a child */
    }
    sbuf_putc(out, '\n');
    /* attributes: each on its own deeper line, output in lexicographic name
       order (the html5lib #document format sorts them). Only elements have
       attributes; a text node's attr_count field holds a span offset. */
    Py_ssize_t order[64];
    Py_ssize_t count = node->type == TH_NODE_ELEMENT ? (node->attr_count < 64 ? node->attr_count : 64) : 0;
    for (Py_ssize_t index = 0; index < count; index++) {
        order[index] = index;
    }
    /* Sort on the displayed name so a namespaced attribute (shown as
       "prefix localname") orders by its space, which precedes a literal colon. */
    char ke_buf[128];
    char cmp_buf[128];
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
        /* foreign attribute name adjustments: xlink:/xml:/xmlns: serialize with a
           space, and SVG/MathML attributes take their mixed-case spelling */
        Py_ssize_t name_len;
        const char *name = th_attr_name(tree, attr->name_atom, &name_len);
        const char *mixed = node->ns != TH_NS_HTML ? foreign_adjust_attr(name, name_len, node->ns) : NULL;
        if (node->ns != TH_NS_HTML && foreign_attr_namespaced(name, name_len)) {
            for (const char *character = name; *character; character++) {
                sbuf_putc(out, *character == ':' ? (Py_UCS4)' ' : (Py_UCS4)*character);
            }
        } else if (mixed != NULL) {
            sbuf_puts(out, mixed);
        } else {
            sbuf_put_utf8(out, name, name_len);
        }
        sbuf_puts(out, "=\"");
        sbuf_put_ucs4(out, attr->value, attr->value_len);
        sbuf_putc(out, '"');
        sbuf_putc(out, '\n');
    }
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        serialize_node(out, tree, child, depth + 1);
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

/* Append text with the WHATWG HTML escapes; in_attr selects the attribute-value
   set ('&', '"', nbsp) versus the text set ('&', '<', '>', nbsp). */
static void sbuf_put_escaped(sbuf *out, const Py_UCS4 *text, Py_ssize_t len, int in_attr) {
    for (Py_ssize_t index = 0; index < len; index++) {
        Py_UCS4 character = text[index];
        if (character == '&') {
            sbuf_puts(out, "&amp;");
        } else if (character == 0xA0) {
            sbuf_puts(out, "&nbsp;");
        } else if (in_attr && character == '"') {
            sbuf_puts(out, "&quot;");
        } else if (!in_attr && character == '<') {
            sbuf_puts(out, "&lt;");
        } else if (!in_attr && character == '>') {
            sbuf_puts(out, "&gt;");
        } else {
            sbuf_putc(out, character);
        }
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

/* The doctype name length: build_doctype_text stores "name" optionally followed
   by ` "public" "system"`, but HTML serialization emits only the name. */
static Py_ssize_t doctype_name_len(const th_node *node) {
    Py_ssize_t index = 0;
    while (index < node->text_len && node->text[index] != ' ') {
        index++;
    }
    return index;
}

static void serialize_html(sbuf *out, th_tree *tree, th_node *node) {
    switch (node->type) { /* GCOVR_EXCL_BR_LINE: th_node_type is exhaustive; the implicit default is unreachable */
    case TH_NODE_ELEMENT: {
        sbuf_putc(out, '<');
        sbuf_put_ucs4(out, node->text, node->text_len);
        for (Py_ssize_t index = 0; index < node->attr_count; index++) {
            th_node_attr *attr = &node->attrs[index];
            sbuf_putc(out, ' ');
            Py_ssize_t name_len;
            const char *name = th_attr_name(tree, attr->name_atom, &name_len);
            sbuf_put_utf8(out, name, name_len);
            sbuf_puts(out, "=\"");
            sbuf_put_escaped(out, attr->value, attr->value_len, 1);
            sbuf_putc(out, '"');
        }
        sbuf_putc(out, '>');
        if (node->ns == TH_NS_HTML && is_void_atom(node->atom)) {
            break; /* void elements have no children or end tag */
        }
        int raw = is_rawtext_element(node);
        for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
            /* a rawtext element's children are always text nodes */
            if (raw && child->type == TH_NODE_TEXT) { /* GCOVR_EXCL_BR_LINE */
                sbuf_put_ucs4(out, need_text(tree, child), child->text_len);
            } else {
                serialize_html(out, tree, child);
            }
        }
        sbuf_putc(out, '<');
        sbuf_putc(out, '/');
        sbuf_put_ucs4(out, node->text, node->text_len);
        sbuf_putc(out, '>');
        break;
    }
    case TH_NODE_TEXT:
        sbuf_put_escaped(out, need_text(tree, node), node->text_len, 0);
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
    case TH_NODE_CONTENT:
    case TH_NODE_DOCUMENT:
        for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
            serialize_html(out, tree, child);
        }
        break;
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

Py_UCS4 *th_node_html(th_tree *tree, th_node *node, Py_ssize_t *out_len) {
    sbuf out = {NULL, 0, 0, 0};
    serialize_html(&out, tree, node);
    return sbuf_finish(&out, out_len);
}
