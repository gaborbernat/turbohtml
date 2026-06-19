/* GitHub-Flavored-Markdown export, #included into treebuilder.c after
   treebuilder_serialize.h so it shares the sbuf buffer, need_text(), the tag
   atoms, and the attribute lookup. The walk is a recursive descent over the
   finished tree (the same shape collect_text() uses): block elements are laid
   out vertically with collapsed blank-line margins, inline elements wrap their
   content in markdown markers, and runs of whitespace collapse to one space the
   way the CSS normal flow does. Output is opinionated GFM with no options, so a
   `scrape -> markdown` pipeline needs no second dependency.

   The single non-obvious piece is whitespace. Text whitespace is never emitted
   eagerly: a run sets space_pending, and the deferred space is flushed (as one
   space) only just before the next real character, and only when the current
   line already holds content. That one rule collapses runs, drops the space at
   block and line starts, and — because a closing marker does not flush — moves a
   trailing inner space out of `**bold** ` instead of leaving `**bold **`, which
   is invalid markdown. */

/* ----------------------------------------------------------- block classes */

/* A block-level element opens its own line(s); everything else is inline and
   flows into the surrounding text. Unknown (custom) tags flow inline, matching
   how a browser lays out an undisplayed custom element's text. */
static int is_md_block(uint16_t atom) {
    switch (atom) {
    case TH_TAG_HTML:
    case TH_TAG_BODY:
    case TH_TAG_P:
    case TH_TAG_DIV:
    case TH_TAG_SECTION:
    case TH_TAG_ARTICLE:
    case TH_TAG_HEADER:
    case TH_TAG_FOOTER:
    case TH_TAG_NAV:
    case TH_TAG_ASIDE:
    case TH_TAG_MAIN:
    case TH_TAG_FIGURE:
    case TH_TAG_FIGCAPTION:
    case TH_TAG_ADDRESS:
    case TH_TAG_BLOCKQUOTE:
    case TH_TAG_PRE:
    case TH_TAG_HR:
    case TH_TAG_H1:
    case TH_TAG_H2:
    case TH_TAG_H3:
    case TH_TAG_H4:
    case TH_TAG_H5:
    case TH_TAG_H6:
    case TH_TAG_UL:
    case TH_TAG_OL:
    case TH_TAG_LI:
    case TH_TAG_DL:
    case TH_TAG_DT:
    case TH_TAG_DD:
    case TH_TAG_MENU:
    case TH_TAG_DETAILS:
    case TH_TAG_SUMMARY:
    case TH_TAG_TABLE:
        return 1;
    default:
        return 0;
    }
}

/* Tags whose entire subtree contributes nothing to a text/markdown rendering:
   document metadata and scripts. */
static int is_md_skipped(uint16_t atom) {
    return atom == TH_TAG_HEAD || atom == TH_TAG_SCRIPT || atom == TH_TAG_STYLE;
}

/* -------------------------------------------------------------- the cursor */

/* An emphasis/strikethrough marker whose opening run is deferred until the first
   visible character of its content, so a leading inner space lands outside the
   marker (`a<b> x</b>` -> `a **x**`, never the invalid `a** x**`). The frames
   chain through the C call stack, outermost reachable via prev. */
typedef struct md_pending {
    const char *marker;
    struct md_pending *prev;
    int emitted;
} md_pending;

typedef struct {
    sbuf out;
    th_tree *tree;
    sbuf prefix;          /* what every continuation line starts with: list indent + "> " quotes */
    md_pending *pending;  /* innermost inline marker whose open run is still deferred */
    int started;          /* has any block content been emitted yet */
    int line_has_content; /* real content past the prefix/marker on the current line */
    int space_pending;    /* a collapsed-away whitespace run is owed one space */
    int drop_space;       /* swallow the next pending space (block/inline start) without emitting */
    int pending_loose;    /* the previous block wants a blank line after it */
    int suppress_break;   /* the next block attaches to the current (list marker) line */
    int tight;            /* inside a list item: inline runs do not add blank lines */
} md_ctx;

static int md_is_ws(Py_UCS4 c) {
    /* the tokenizer has already normalized CR to LF, so a tree text node never
       holds a carriage return; classifying it here would be a dead branch */
    return c == ' ' || c == '\t' || c == '\n' || c == '\f';
}

/* Append n spaces to the continuation prefix and return the start offset, so the
   caller can pop them back off after the nested block. */
static Py_ssize_t md_push_spaces(md_ctx *ctx, Py_ssize_t n) {
    Py_ssize_t base = ctx->prefix.len;
    for (Py_ssize_t i = 0; i < n; i++) {
        sbuf_putc(&ctx->prefix, ' ');
    }
    return base;
}

/* Write the continuation prefix at the head of a fresh line. */
static void md_write_prefix(md_ctx *ctx) {
    sbuf_put_run(&ctx->out, ctx->prefix.data, ctx->prefix.len);
}

/* Write the prefix for a blank separator line with its trailing spaces trimmed,
   so a plain blank line stays empty and a blockquote shows ">" not "> ". */
static void md_write_blank_prefix(md_ctx *ctx) {
    Py_ssize_t len = ctx->prefix.len;
    while (len > 0 && ctx->prefix.data[len - 1] == ' ') {
        len--;
    }
    sbuf_put_run(&ctx->out, ctx->prefix.data, len);
}

/* Position the cursor at the start of a fresh, prefixed line for the next block,
   collapsing the margin with the previous block (a blank line when either side
   is loose). loose marks whether this block wants blank lines around it. */
static void md_block_line(md_ctx *ctx, int loose) {
    if (!ctx->started) {
        ctx->started = 1;
        md_write_prefix(ctx);
    } else if (ctx->suppress_break) {
        ctx->suppress_break = 0;
    } else {
        sbuf_putc(&ctx->out, '\n');
        if ((ctx->pending_loose || loose) && !ctx->tight) {
            md_write_blank_prefix(ctx);
            sbuf_putc(&ctx->out, '\n');
        }
        md_write_prefix(ctx);
        ctx->line_has_content = 0;
    }
    ctx->pending_loose = loose;
    ctx->space_pending = 0;
    ctx->drop_space = 1;
}

/* Start a new continuation line inside the current block (a <br> or a code-block
   line break): one newline plus the prefix, content reset but the block open. */
static void md_newline(md_ctx *ctx) {
    sbuf_putc(&ctx->out, '\n');
    md_write_prefix(ctx);
    ctx->line_has_content = 0;
    ctx->space_pending = 0;
    ctx->drop_space = 1;
}

/* Emit the one space a collapsed whitespace run owes, unless it falls at a line
   start or has been marked for dropping (the start of a block). */
static void md_flush_space(md_ctx *ctx) {
    int drop = ctx->drop_space;
    ctx->drop_space = 0;
    if (!ctx->space_pending) {
        return;
    }
    ctx->space_pending = 0;
    /* every line start sets drop_space, so a line-start space is already covered
       by drop and no separate line_has_content test is needed here */
    if (drop) {
        return;
    }
    sbuf_putc(&ctx->out, ' ');
}

/* Emit the deferred opening markers from outermost to innermost (skipping any
   already written), so nested emphasis opens in source order. */
static void md_emit_pending(md_ctx *ctx, md_pending *frame) {
    if (frame == NULL || frame->emitted) {
        return;
    }
    md_emit_pending(ctx, frame->prev);
    sbuf_puts(&ctx->out, frame->marker);
    frame->emitted = 1;
    ctx->line_has_content = 1;
}

/* Called just before any visible character: settle the owed space first (so it
   stays outside an emphasis run), then open any markers that were waiting for
   real content. */
static void md_before_visible(md_ctx *ctx) {
    md_flush_space(ctx);
    md_emit_pending(ctx, ctx->pending);
}

/* ----------------------------------------------------------- inline output */

/* Characters that begin a markdown construct and so are backslash-escaped in
   running text. Leading line markers (#, >, -, +) are handled separately, only
   at the very start of a line. */
static int md_needs_escape(Py_UCS4 c) {
    return c == '\\' || c == '`' || c == '*' || c == '_' || c == '[' || c == ']';
}

static void md_put_char(md_ctx *ctx, Py_UCS4 c) {
    int line_start_marker = !ctx->line_has_content && (c == '#' || c == '>' || c == '-' || c == '+');
    if (md_needs_escape(c) || line_start_marker) {
        sbuf_putc(&ctx->out, '\\');
    }
    sbuf_putc(&ctx->out, c);
    ctx->line_has_content = 1;
}

/* At a line start, "12. " or "3) " would be read as an ordered-list item, so a
   leading run of digits before a dot or paren is escaped. Returns how many code
   points were consumed (0 when the run is not list-like). */
static Py_ssize_t md_escape_line_number(md_ctx *ctx, const Py_UCS4 *text, Py_ssize_t i, Py_ssize_t len) {
    /* the caller only enters here on a digit, so the run is at least one long */
    Py_ssize_t j = i;
    while (j < len && text[j] >= '0' && text[j] <= '9') {
        j++;
    }
    if (j >= len || (text[j] != '.' && text[j] != ')')) {
        return 0;
    }
    sbuf_put_run(&ctx->out, &text[i], j - i);
    sbuf_putc(&ctx->out, '\\');
    sbuf_putc(&ctx->out, text[j]);
    ctx->line_has_content = 1;
    return j + 1 - i;
}

/* Emit inline text with normal-flow whitespace collapsing and markdown escaping.
   Prose is mostly plain runs, so after the first character of a word is placed
   (which resolves the deferred space, markers and escapes) the rest of the run —
   no whitespace, nothing to escape — is bulk-copied in one memcpy. */
static void md_emit_text(md_ctx *ctx, const Py_UCS4 *text, Py_ssize_t len) {
    Py_ssize_t i = 0;
    while (i < len) {
        Py_UCS4 c = text[i];
        if (md_is_ws(c)) {
            ctx->space_pending = 1;
            i++;
            continue;
        }
        md_before_visible(ctx);
        if (!ctx->line_has_content && c >= '0' && c <= '9') {
            Py_ssize_t consumed = md_escape_line_number(ctx, text, i, len);
            if (consumed > 0) {
                i += consumed;
                continue;
            }
        }
        md_put_char(ctx, c);
        i++;
        Py_ssize_t start = i;
        while (i < len && !md_is_ws(text[i]) && !md_needs_escape(text[i])) {
            i++;
        }
        if (i > start) {
            sbuf_put_run(&ctx->out, &text[start], i - start);
        }
    }
}

/* Write decimal digits of a non-negative number and return how many. */
static Py_ssize_t md_put_decimal(sbuf *out, Py_ssize_t n) {
    Py_UCS4 digits[20];
    Py_ssize_t count = 0;
    do {
        digits[count++] = (Py_UCS4)('0' + (int)(n % 10));
        n /= 10;
    } while (n > 0);
    for (Py_ssize_t i = count - 1; i >= 0; i--) {
        sbuf_putc(out, digits[i]);
    }
    return count;
}

/* The value of one attribute by interned name, or NULL with *len 0 when the
   attribute is absent or valueless. */
static const Py_UCS4 *md_attr(th_tree *tree, th_node *node, const char *name, Py_ssize_t *len) {
    Py_ssize_t index = th_node_attr_find(tree, node, name, (Py_ssize_t)strlen(name));
    if (index < 0 || node->attrs[index].value == NULL) {
        *len = 0;
        return NULL;
    }
    *len = node->attrs[index].value_len;
    return node->attrs[index].value;
}

static void md_render_inline(md_ctx *ctx, th_node *node);

static void md_inline_children(md_ctx *ctx, th_node *node) {
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        md_render_inline(ctx, child);
    }
}

/* Wrap an inline element's content in a marker (** , * , ~~). The open run is
   deferred (md_before_visible writes it at the first visible character) so a
   leading inner space moves outside; the close run is written only if the open
   one was, so an empty <b></b> leaves nothing behind. The owed space is left
   pending across the close, so a trailing inner space also lands outside. */
static void md_wrap(md_ctx *ctx, th_node *node, const char *marker) {
    md_pending frame = {marker, ctx->pending, 0};
    ctx->pending = &frame;
    md_inline_children(ctx, node);
    ctx->pending = frame.prev;
    if (frame.emitted) {
        sbuf_puts(&ctx->out, marker);
    }
}

/* The longest run of backticks anywhere in s, so an inline code span can fence
   with one more backtick than that and never be split by its own content. */
static Py_ssize_t md_max_backtick_run(const Py_UCS4 *s, Py_ssize_t len) {
    Py_ssize_t best = 0;
    Py_ssize_t run = 0;
    for (Py_ssize_t i = 0; i < len; i++) {
        if (s[i] == '`') {
            run++;
            if (run > best) {
                best = run;
            }
        } else {
            run = 0;
        }
    }
    return best;
}

static void md_emit_code_span(md_ctx *ctx, th_node *node) {
    Py_ssize_t len;
    Py_UCS4 *content = th_node_text(ctx->tree, node, &len);
    if (content == NULL) {   /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        ctx->out.failed = 1; /* GCOVR_EXCL_LINE: allocation-failure path */
        return;              /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    md_before_visible(ctx);
    Py_ssize_t fence = md_max_backtick_run(content, len) + 1;
    int pad = len > 0 && (content[0] == '`' || content[len - 1] == '`');
    for (Py_ssize_t i = 0; i < fence; i++) {
        sbuf_putc(&ctx->out, '`');
    }
    if (pad) {
        sbuf_putc(&ctx->out, ' ');
    }
    sbuf_put_run(&ctx->out, content, len);
    if (pad) {
        sbuf_putc(&ctx->out, ' ');
    }
    for (Py_ssize_t i = 0; i < fence; i++) {
        sbuf_putc(&ctx->out, '`');
    }
    ctx->line_has_content = 1;
    PyMem_Free(content);
}

/* Write a URL/destination verbatim (no markdown escaping); a space inside it is
   wrapped in angle brackets so the destination stays a single token. */
static void md_emit_url(md_ctx *ctx, const Py_UCS4 *url, Py_ssize_t len) {
    int has_space = 0;
    for (Py_ssize_t i = 0; i < len; i++) {
        if (url[i] == ' ') {
            has_space = 1;
        }
    }
    if (has_space) {
        sbuf_putc(&ctx->out, '<');
        sbuf_put_run(&ctx->out, url, len);
        sbuf_putc(&ctx->out, '>');
    } else {
        sbuf_put_run(&ctx->out, url, len);
    }
}

static void md_emit_link(md_ctx *ctx, th_node *node) {
    Py_ssize_t href_len;
    const Py_UCS4 *href = md_attr(ctx->tree, node, "href", &href_len);
    if (href == NULL) {
        md_inline_children(ctx, node);
        return;
    }
    md_before_visible(ctx);
    sbuf_putc(&ctx->out, '[');
    ctx->line_has_content = 1;
    ctx->drop_space = 1;
    md_inline_children(ctx, node);
    sbuf_puts(&ctx->out, "](");
    md_emit_url(ctx, href, href_len);
    Py_ssize_t title_len;
    const Py_UCS4 *title = md_attr(ctx->tree, node, "title", &title_len);
    if (title != NULL) {
        sbuf_puts(&ctx->out, " \"");
        sbuf_put_run(&ctx->out, title, title_len);
        sbuf_putc(&ctx->out, '"');
    }
    sbuf_putc(&ctx->out, ')');
}

static void md_emit_image(md_ctx *ctx, th_node *node) {
    md_before_visible(ctx);
    Py_ssize_t alt_len;
    const Py_UCS4 *alt = md_attr(ctx->tree, node, "alt", &alt_len);
    Py_ssize_t src_len;
    const Py_UCS4 *src = md_attr(ctx->tree, node, "src", &src_len);
    sbuf_puts(&ctx->out, "![");
    if (alt != NULL) {
        sbuf_put_run(&ctx->out, alt, alt_len);
    }
    sbuf_puts(&ctx->out, "](");
    if (src != NULL) {
        md_emit_url(ctx, src, src_len);
    }
    sbuf_putc(&ctx->out, ')');
    ctx->line_has_content = 1;
}

static void md_render_block(md_ctx *ctx, th_node *node);
static void md_block_children(md_ctx *ctx, th_node *node);

/* Render one node encountered in an inline run. A block element nested in inline
   flow (rare, e.g. a <div> inside a <span>) is laid out as its own block. */
static void md_render_inline(md_ctx *ctx, th_node *node) {
    if (node->type == TH_NODE_TEXT) {
        md_emit_text(ctx, need_text(ctx->tree, node), node->text_len);
        return;
    }
    if (node->type != TH_NODE_ELEMENT && node->type != TH_NODE_CONTENT) {
        return;
    }
    uint16_t atom = node->ns == TH_NS_HTML ? node->atom : TH_TAG_UNKNOWN;
    switch (atom) {
    case TH_TAG_STRONG:
    case TH_TAG_B:
        md_wrap(ctx, node, "**");
        return;
    case TH_TAG_EM:
    case TH_TAG_I:
        md_wrap(ctx, node, "*");
        return;
    case TH_TAG_DEL:
    case TH_TAG_S:
    case TH_TAG_STRIKE:
        md_wrap(ctx, node, "~~");
        return;
    case TH_TAG_CODE:
        md_emit_code_span(ctx, node);
        return;
    case TH_TAG_A:
        md_emit_link(ctx, node);
        return;
    case TH_TAG_IMG:
        md_emit_image(ctx, node);
        return;
    case TH_TAG_BR:
        sbuf_puts(&ctx->out, "  ");
        md_newline(ctx);
        return;
    case TH_TAG_WBR:
        return;
    default:
        break;
    }
    if (is_md_skipped(atom)) {
        return;
    }
    if (is_md_block(atom)) {
        md_render_block(ctx, node);
        return;
    }
    md_inline_children(ctx, node);
}

/* ------------------------------------------------------------ block output */

/* Whether the element's first meaningful child is inline content rather than a
   nested block, deciding if a list item's text rides on the bullet line. */
static int md_leads_with_inline(md_ctx *ctx, th_node *node) {
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        if (child->type == TH_NODE_TEXT) {
            const Py_UCS4 *text = need_text(ctx->tree, child);
            for (Py_ssize_t i = 0; i < child->text_len; i++) {
                if (!md_is_ws(text[i])) {
                    return 1; /* leading visible text rides on the bullet line */
                }
            }
            continue; /* whitespace-only: keep looking past it */
        }
        if (child->type != TH_NODE_ELEMENT) {
            continue;
        }
        uint16_t atom = child->ns == TH_NS_HTML ? child->atom : TH_TAG_UNKNOWN;
        if (is_md_skipped(atom)) {
            continue;
        }
        return !is_md_block(atom);
    }
    return 0;
}

/* Lay out the children of a block container: consecutive inline children form
   one paragraph-like run, and each block child recurses. */
static void md_block_children(md_ctx *ctx, th_node *node) {
    int in_run = 0;
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        uint16_t atom = TH_TAG_UNKNOWN;
        int block = 0;
        if (child->type == TH_NODE_ELEMENT) {
            atom = child->ns == TH_NS_HTML ? child->atom : TH_TAG_UNKNOWN;
            if (is_md_skipped(atom)) {
                continue;
            }
            block = is_md_block(atom);
        } else if (child->type == TH_NODE_CONTENT) {
            md_block_children(ctx, child);
            continue;
        } else if (child->type != TH_NODE_TEXT) {
            continue;
        }
        if (block) {
            in_run = 0;
            md_render_block(ctx, child);
            continue;
        }
        if (!in_run) {
            int only_ws = child->type == TH_NODE_TEXT;
            if (only_ws) {
                const Py_UCS4 *text = need_text(ctx->tree, child);
                for (Py_ssize_t i = 0; i < child->text_len; i++) {
                    if (!md_is_ws(text[i])) {
                        only_ws = 0;
                        break;
                    }
                }
            }
            if (only_ws) {
                continue;
            }
            md_block_line(ctx, ctx->tight ? 0 : 1);
            in_run = 1;
        }
        md_render_inline(ctx, child);
    }
}

static void md_render_list(md_ctx *ctx, th_node *node, int ordered) {
    Py_ssize_t number = 1;
    if (ordered) {
        Py_ssize_t start_len;
        const Py_UCS4 *start = md_attr(ctx->tree, node, "start", &start_len);
        if (start != NULL) {
            Py_ssize_t value = 0;
            int seen = 0;
            for (Py_ssize_t i = 0; i < start_len; i++) {
                if (start[i] >= '0' && start[i] <= '9') {
                    value = value * 10 + (start[i] - '0');
                    seen = 1;
                } else {
                    break;
                }
            }
            if (seen) {
                number = value;
            }
        }
    }
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        if (child->type != TH_NODE_ELEMENT || child->ns != TH_NS_HTML || child->atom != TH_TAG_LI) {
            continue;
        }
        md_block_line(ctx, 0);
        Py_ssize_t width;
        if (ordered) {
            width = md_put_decimal(&ctx->out, number) + 2;
            sbuf_puts(&ctx->out, ". ");
            number++;
        } else {
            sbuf_puts(&ctx->out, "- ");
            width = 2;
        }
        ctx->line_has_content = 1;
        Py_ssize_t base = md_push_spaces(ctx, width);
        int saved_tight = ctx->tight;
        ctx->tight = 1;
        ctx->suppress_break = md_leads_with_inline(ctx, child);
        md_block_children(ctx, child);
        ctx->tight = saved_tight;
        ctx->prefix.len = base;
    }
}

/* Emit a single table cell's inline content with internal newlines flattened to
   spaces and pipes escaped, so it stays on one row. */
static void md_emit_cell(md_ctx *ctx, th_node *node) {
    sbuf saved_out = ctx->out;
    sbuf saved_prefix = ctx->prefix;
    int saved_started = ctx->started;
    int saved_line = ctx->line_has_content;
    int saved_space = ctx->space_pending;
    int saved_drop = ctx->drop_space;
    sbuf cell = {NULL, 0, 0, 0};
    ctx->out = cell;
    ctx->prefix = (sbuf){NULL, 0, 0, 0};
    ctx->line_has_content = 1;
    ctx->space_pending = 0;
    ctx->drop_space = 1;
    md_inline_children(ctx, node);
    sbuf rendered = ctx->out;
    PyMem_Free(ctx->prefix.data);
    ctx->out = saved_out;
    ctx->prefix = saved_prefix;
    ctx->started = saved_started;
    ctx->line_has_content = saved_line;
    ctx->space_pending = saved_space;
    ctx->drop_space = saved_drop;
    int space_run = 0;
    for (Py_ssize_t i = 0; i < rendered.len; i++) {
        Py_UCS4 c = rendered.data[i];
        if (c == '\n' || c == ' ') {
            space_run = 1;
            continue;
        }
        if (space_run) {
            sbuf_putc(&ctx->out, ' ');
            space_run = 0;
        }
        if (c == '|') {
            sbuf_puts(&ctx->out, "\\|");
        } else {
            sbuf_putc(&ctx->out, c);
        }
    }
    PyMem_Free(rendered.data);
}

/* A row's element children come only from HTML table parsing (foreign content is
   foster-parented out of the table), so the td/th atoms already imply the HTML
   namespace and no separate ns test is needed in these loops. */
static Py_ssize_t md_row_cells(th_node *row) {
    Py_ssize_t count = 0;
    for (th_node *cell = row->first_child; cell != NULL; cell = cell->next_sibling) {
        if (cell->type == TH_NODE_ELEMENT && (cell->atom == TH_TAG_TD || cell->atom == TH_TAG_TH)) {
            count++;
        }
    }
    return count;
}

static void md_emit_row(md_ctx *ctx, th_node *row, Py_ssize_t columns) {
    sbuf_puts(&ctx->out, "| ");
    Py_ssize_t emitted = 0;
    for (th_node *cell = row->first_child; cell != NULL; cell = cell->next_sibling) {
        if (cell->type != TH_NODE_ELEMENT || (cell->atom != TH_TAG_TD && cell->atom != TH_TAG_TH)) {
            continue;
        }
        md_emit_cell(ctx, cell);
        sbuf_puts(&ctx->out, " | ");
        emitted++;
    }
    for (; emitted < columns; emitted++) {
        sbuf_puts(&ctx->out, " | ");
    }
    ctx->line_has_content = 1;
}

/* Collect the table's rows in document order across an optional thead/tbody/tfoot
   wrapper, append each into rows, and return the widest row's column count. */
static Py_ssize_t md_collect_rows(th_node *node, th_node **rows, Py_ssize_t *count) {
    Py_ssize_t columns = 0;
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        if (child->type != TH_NODE_ELEMENT) {
            continue;
        }
        if (child->atom == TH_TAG_TR) {
            /* cap counts every child and grandchild, so it bounds the rows by
               construction and indexing it needs no run-time guard */
            rows[*count] = child;
            (*count)++;
            Py_ssize_t cells = md_row_cells(child);
            if (cells > columns) {
                columns = cells;
            }
        } else if (child->atom == TH_TAG_THEAD || child->atom == TH_TAG_TBODY || child->atom == TH_TAG_TFOOT) {
            Py_ssize_t nested = md_collect_rows(child, rows, count);
            if (nested > columns) {
                columns = nested;
            }
        }
    }
    return columns;
}

static void md_render_table(md_ctx *ctx, th_node *node) {
    Py_ssize_t cap = 0;
    for (th_node *body = node->first_child; body != NULL; body = body->next_sibling) {
        cap += 1;
        for (th_node *row = body->first_child; row != NULL; row = row->next_sibling) {
            cap += 1;
        }
    }
    th_node **rows = PyMem_Malloc((size_t)(cap > 0 ? cap : 1) * sizeof(th_node *));
    if (rows == NULL) {      /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        ctx->out.failed = 1; /* GCOVR_EXCL_LINE: allocation-failure path */
        return;              /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    Py_ssize_t count = 0;
    Py_ssize_t columns = md_collect_rows(node, rows, &count);
    if (count == 0 || columns == 0) {
        PyMem_Free(rows);
        return;
    }
    md_block_line(ctx, 1);
    md_emit_row(ctx, rows[0], columns);
    md_newline(ctx);
    sbuf_puts(&ctx->out, "| ");
    for (Py_ssize_t c = 0; c < columns; c++) {
        sbuf_puts(&ctx->out, "--- | ");
    }
    ctx->line_has_content = 1;
    for (Py_ssize_t r = 1; r < count; r++) {
        md_newline(ctx);
        md_emit_row(ctx, rows[r], columns);
    }
    PyMem_Free(rows);
}

static void md_render_pre(md_ctx *ctx, th_node *node) {
    th_node *code = node->first_child;
    th_node *content = node;
    Py_ssize_t lang_len = 0;
    const Py_UCS4 *lang = NULL;
    if (code != NULL && code->type == TH_NODE_ELEMENT && code->ns == TH_NS_HTML && code->atom == TH_TAG_CODE &&
        code->next_sibling == NULL) {
        content = code;
        Py_ssize_t cls_len;
        const Py_UCS4 *cls = md_attr(ctx->tree, code, "class", &cls_len);
        if (cls != NULL) {
            const char *want = "language-";
            Py_ssize_t want_len = 9;
            if (cls_len > want_len) {
                int match = 1;
                for (Py_ssize_t i = 0; i < want_len; i++) {
                    if (cls[i] != (Py_UCS4)(unsigned char)want[i]) {
                        match = 0;
                        break;
                    }
                }
                if (match) {
                    lang = cls + want_len;
                    lang_len = cls_len - want_len;
                    for (Py_ssize_t i = 0; i < lang_len; i++) {
                        if (md_is_ws(lang[i])) {
                            lang_len = i;
                            break;
                        }
                    }
                }
            }
        }
    }
    Py_ssize_t text_len;
    Py_UCS4 *text = th_node_text(ctx->tree, content, &text_len);
    if (text == NULL) {      /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        ctx->out.failed = 1; /* GCOVR_EXCL_LINE: allocation-failure path */
        return;              /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    Py_ssize_t fence = md_max_backtick_run(text, text_len);
    fence = fence + 1 > 3 ? fence + 1 : 3;
    md_block_line(ctx, 1);
    for (Py_ssize_t i = 0; i < fence; i++) {
        sbuf_putc(&ctx->out, '`');
    }
    if (lang != NULL) {
        sbuf_put_run(&ctx->out, lang, lang_len);
    }
    ctx->line_has_content = 1;
    /* drop one trailing newline so the closing fence is not preceded by a blank */
    Py_ssize_t end = text_len;
    if (end > 0 && text[end - 1] == '\n') {
        end--;
    }
    md_newline(ctx);
    for (Py_ssize_t i = 0; i < end; i++) {
        if (text[i] == '\n') {
            md_newline(ctx);
        } else {
            sbuf_putc(&ctx->out, text[i]);
            ctx->line_has_content = 1;
        }
    }
    md_newline(ctx);
    for (Py_ssize_t i = 0; i < fence; i++) {
        sbuf_putc(&ctx->out, '`');
    }
    ctx->line_has_content = 1;
    PyMem_Free(text);
}

static void md_render_block(md_ctx *ctx, th_node *node) {
    /* only an HTML element is ever classified as a block, so the namespace check
       the callers already made guarantees node is HTML here */
    uint16_t atom = node->atom;
    switch (atom) {
    case TH_TAG_H1:
    case TH_TAG_H2:
    case TH_TAG_H3:
    case TH_TAG_H4:
    case TH_TAG_H5:
    case TH_TAG_H6: {
        md_block_line(ctx, 1);
        int level = atom - TH_TAG_H1 + 1;
        for (int i = 0; i < level; i++) {
            sbuf_putc(&ctx->out, '#');
        }
        sbuf_putc(&ctx->out, ' ');
        ctx->line_has_content = 1;
        ctx->drop_space = 1;
        md_inline_children(ctx, node);
        return;
    }
    case TH_TAG_HR:
        md_block_line(ctx, 1);
        sbuf_puts(&ctx->out, "---");
        ctx->line_has_content = 1;
        return;
    case TH_TAG_UL:
    case TH_TAG_MENU:
        md_render_list(ctx, node, 0);
        return;
    case TH_TAG_OL:
        md_render_list(ctx, node, 1);
        return;
    case TH_TAG_PRE:
        md_render_pre(ctx, node);
        return;
    case TH_TAG_TABLE:
        md_render_table(ctx, node);
        return;
    case TH_TAG_BLOCKQUOTE: {
        Py_ssize_t base = ctx->prefix.len;
        if (ctx->started) {
            /* close the previous block and open the separator with the OUTER
               prefix, so the blank line is not itself quoted, before adding the
               "> " that every line inside the quote carries */
            sbuf_putc(&ctx->out, '\n');
            if (!ctx->tight) {
                md_write_blank_prefix(ctx);
                sbuf_putc(&ctx->out, '\n');
            }
            sbuf_puts(&ctx->prefix, "> ");
            md_write_prefix(ctx);
            ctx->line_has_content = 0;
            ctx->space_pending = 0;
            ctx->drop_space = 1;
            ctx->pending_loose = 1;
            ctx->suppress_break = 1;
        } else {
            sbuf_puts(&ctx->prefix, "> ");
        }
        int saved_tight = ctx->tight;
        ctx->tight = 0;
        md_block_children(ctx, node);
        ctx->tight = saved_tight;
        ctx->prefix.len = base;
        return;
    }
    default:
        md_block_children(ctx, node);
        return;
    }
}

/* Trim leading and trailing whitespace from the finished buffer in place, so the
   document neither starts with blank lines nor trails them. */
static void md_trim(sbuf *out) {
    Py_ssize_t start = 0;
    while (start < out->len && md_is_ws(out->data[start])) {
        start++;
    }
    Py_ssize_t end = out->len;
    while (end > start && md_is_ws(out->data[end - 1])) {
        end--;
    }
    if (start > 0) {
        memmove(out->data, out->data + start, (size_t)(end - start) * sizeof(Py_UCS4));
    }
    out->len = end - start;
}

Py_UCS4 *th_node_markdown(th_tree *tree, th_node *node, Py_ssize_t *out_len) {
    md_ctx ctx = {{NULL, 0, 0, 0}, tree, {NULL, 0, 0, 0}, NULL, 0, 0, 0, 0, 0, 0, 0};
    sbuf_presize_for_root(&ctx.out, tree, node);
    if (node->type == TH_NODE_TEXT) {
        ctx.started = 1;
        ctx.line_has_content = 1;
        md_emit_text(&ctx, need_text(tree, node), node->text_len);
    } else if (is_md_block(node->ns == TH_NS_HTML ? node->atom : TH_TAG_UNKNOWN)) {
        md_render_block(&ctx, node);
    } else {
        md_block_children(&ctx, node);
    }
    PyMem_Free(ctx.prefix.data);
    md_trim(&ctx.out);
    return sbuf_finish(&ctx.out, out_len);
}
