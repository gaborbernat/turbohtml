/* Readability-style main-content extraction, #included into treebuilder.c after
   treebuilder_text.h so it shares need_text(), the tag atoms, and the attribute
   lookup. It scores the DOM by content density -- text length, comma count, tag
   weight and class/id weight, discounted by link density, the well-known
   readability heuristic -- and returns the single highest-scoring container
   element. Everything here is pure C: tree_type.c wraps the returned node (or
   renders its text with th_node_layout_text) under the per-tree critical section,
   so no Python API is touched while the structure is walked. */

/* A paragraph shorter than this is treated as noise, not content. */
#define READ_MIN_PARAGRAPH_CHARS 25
/* The text-length bonus saturates here (each 100 chars adds a point, up to 3). */
#define READ_CHAR_SCORE_CAP 3
/* Candidate array growth: small initial block, doubled when full. */
#define READ_INITIAL_CANDIDATES 8

/* Boilerplate tags whose subtree never holds main content; their text is excluded
   from the density counts too. <form> is deliberately absent: it stays in the walk
   so its negative tag weight applies when it parents a paragraph. */
static const uint16_t read_skip_tags[] = {
    TH_TAG_SCRIPT, TH_TAG_STYLE,  TH_TAG_NOSCRIPT, TH_TAG_NAV,  TH_TAG_ASIDE,  TH_TAG_FOOTER,   TH_TAG_HEADER,
    TH_TAG_BUTTON, TH_TAG_SELECT, TH_TAG_TEXTAREA, TH_TAG_MENU, TH_TAG_DIALOG, TH_TAG_TEMPLATE,
};

/* The text containers that earn a content score from their own text. */
static const uint16_t read_paragraph_tags[] = {TH_TAG_P, TH_TAG_TD, TH_TAG_PRE};

/* class/id substrings that mark an element as content (raise its weight). */
static const char *const read_positive_words[] = {
    "article", "body", "content", "entry", "hentry", "main", "page", "post", "text", "blog", "story",
};

/* class/id substrings that mark an element as boilerplate (lower its weight). */
static const char *const read_negative_words[] = {
    "hidden", "banner", "combx",   "comment", "contact", "foot",    "footer", "masthead", "media",
    "meta",   "promo",  "related", "scroll",  "sidebar", "sponsor", "tags",   "widget",
};

/* class/id substrings that disqualify a whole subtree before it is scored. */
static const char *const read_unlikely_words[] = {
    "banner",   "combx",   "comment", "community", "disqus",  "extra",  "foot",       "header",
    "menu",     "modal",   "nav",     "popup",     "related", "remark", "rss",        "share",
    "shoutbox", "sidebar", "sponsor", "ad-",       "agegate", "pager",  "pagination",
};

/* class/id substrings that rescue an otherwise-unlikely subtree (it is content
   after all). */
static const char *const read_maybe_words[] = {
    "and", "article", "body", "column", "content", "main", "shadow",
};

/* A growable map from a candidate element to its accumulated content score. The
   candidate set is the parents and grandparents of scored paragraphs, so it stays
   small; a linear find-or-insert is simpler to cover than a hash and fast enough
   for a one-shot extraction. */
typedef struct {
    th_node *node;
    double score;
} read_candidate;

typedef struct {
    th_tree *tree;
    read_candidate *candidates;
    Py_ssize_t count;
    Py_ssize_t cap;
} read_scorer;

/* The text statistics gathered over a subtree: total code points, comma count
   (each comma marks a clause, a weak signal of prose), and the share that sits
   inside an <a>. */
typedef struct {
    Py_ssize_t chars;
    Py_ssize_t commas;
    Py_ssize_t link_chars;
} read_stats;

static int read_atom_in(uint16_t atom, const uint16_t *set, size_t count) {
    for (size_t index = 0; index < count; index++) {
        if (atom == set[index]) {
            return 1;
        }
    }
    return 0;
}

/* Case-insensitive (ASCII) substring test: is `needle` a substring of the
   `hay_len` code points at `hay`? Letters fold, every other byte compares
   literally, matching the readability class/id regexes. */
static int read_ci_contains(const Py_UCS4 *hay, Py_ssize_t hay_len, const char *needle) {
    Py_ssize_t needle_len = (Py_ssize_t)strlen(needle);
    if (needle_len > hay_len) {
        return 0;
    }
    for (Py_ssize_t start = 0; start + needle_len <= hay_len; start++) {
        Py_ssize_t index = 0;
        while (index < needle_len) {
            Py_UCS4 current = hay[start + index];
            Py_UCS4 folded = (current >= 'A' && current <= 'Z') ? (current | 0x20) : current;
            if (folded != (Py_UCS4)(unsigned char)needle[index]) {
                break;
            }
            index++;
        }
        if (index == needle_len) {
            return 1;
        }
    }
    return 0;
}

/* Does the element's class or id attribute contain any of the keywords? */
static int read_match_keywords(th_tree *tree, th_node *node, const char *const *words, size_t count) {
    static const char *const attributes[] = {"class", "id"};
    static const Py_ssize_t attribute_lens[] = {5, 2};
    for (size_t attr = 0; attr < 2; attr++) {
        Py_ssize_t found = th_node_attr_find(tree, node, attributes[attr], attribute_lens[attr]);
        if (found < 0 || node->attrs[found].value == NULL) {
            continue;
        }
        const Py_UCS4 *value = node->attrs[found].value;
        Py_ssize_t value_len = node->attrs[found].value_len;
        for (size_t word = 0; word < count; word++) {
            if (read_ci_contains(value, value_len, words[word])) {
                return 1;
            }
        }
    }
    return 0;
}

/* The +25 / -25 class-weight readability gives an element for content/boilerplate
   class and id hints. */
static double read_class_weight(th_tree *tree, th_node *node) {
    double weight = 0;
    if (read_match_keywords(tree, node, read_negative_words, sizeof(read_negative_words) / sizeof(char *))) {
        weight -= 25;
    }
    if (read_match_keywords(tree, node, read_positive_words, sizeof(read_positive_words) / sizeof(char *))) {
        weight += 25;
    }
    return weight;
}

/* The structural weight readability seeds a candidate with from its tag. */
static double read_tag_base(uint16_t atom) {
    static const uint16_t plus_five[] = {TH_TAG_DIV};
    static const uint16_t plus_three[] = {TH_TAG_PRE, TH_TAG_TD, TH_TAG_BLOCKQUOTE};
    static const uint16_t minus_three[] = {TH_TAG_ADDRESS, TH_TAG_OL, TH_TAG_UL, TH_TAG_DL,
                                           TH_TAG_DD,      TH_TAG_DT, TH_TAG_LI, TH_TAG_FORM};
    static const uint16_t minus_five[] = {TH_TAG_H1, TH_TAG_H2, TH_TAG_H3, TH_TAG_H4, TH_TAG_H5, TH_TAG_H6, TH_TAG_TH};
    if (read_atom_in(atom, plus_five, sizeof(plus_five) / sizeof(uint16_t))) {
        return 5;
    }
    if (read_atom_in(atom, plus_three, sizeof(plus_three) / sizeof(uint16_t))) {
        return 3;
    }
    if (read_atom_in(atom, minus_three, sizeof(minus_three) / sizeof(uint16_t))) {
        return -3;
    }
    if (read_atom_in(atom, minus_five, sizeof(minus_five) / sizeof(uint16_t))) {
        return -5;
    }
    return 0;
}

/* Whether an element starts a boilerplate subtree the walk should not enter: a
   foreign-namespace root, a boilerplate tag, or an unlikely class/id not rescued
   by a "maybe" hint. */
static int read_should_skip(th_tree *tree, th_node *node) {
    if (node->ns != TH_NS_HTML) {
        return 1;
    }
    if (read_atom_in(node->atom, read_skip_tags, sizeof(read_skip_tags) / sizeof(uint16_t))) {
        return 1;
    }
    if (read_match_keywords(tree, node, read_unlikely_words, sizeof(read_unlikely_words) / sizeof(char *)) &&
        !read_match_keywords(tree, node, read_maybe_words, sizeof(read_maybe_words) / sizeof(char *))) {
        return 1;
    }
    return 0;
}

/* Accumulate the text statistics over node's subtree, excluding boilerplate
   subtrees; text inside an <a> also counts toward link_chars. */
static void read_text_stats(th_tree *tree, th_node *node, int in_anchor, read_stats *stats) {
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        if (child->type == TH_NODE_TEXT) {
            stats->chars += child->text_len;
            if (in_anchor) {
                stats->link_chars += child->text_len;
            }
            if (child->text_len > 0) {
                const Py_UCS4 *text = need_text(tree, child);
                for (Py_ssize_t index = 0; index < child->text_len; index++) {
                    if (text[index] == ',') {
                        stats->commas++;
                    }
                }
            }
        } else if (child->type == TH_NODE_ELEMENT) {
            if (child->ns != TH_NS_HTML ||
                read_atom_in(child->atom, read_skip_tags, sizeof(read_skip_tags) / sizeof(uint16_t))) {
                continue;
            }
            read_text_stats(tree, child, in_anchor || child->atom == TH_TAG_A, stats);
        }
    }
}

/* The fraction of a candidate's text that lives inside links; prose scores high
   when little of it is link text. */
static double read_link_density(th_tree *tree, th_node *node) {
    read_stats stats = {0, 0, 0};
    read_text_stats(tree, node, 0, &stats);
    if (stats.chars == 0) { /* GCOVR_EXCL_BR_LINE: a scored candidate always holds a >=25-char paragraph */
        return 0;           /* GCOVR_EXCL_LINE: the guard only prevents a division by zero that cannot occur */
    }
    return (double)stats.link_chars / (double)stats.chars;
}

/* Add `delta` to node's candidate score, seeding a fresh entry with its tag and
   class/id weight on first sight. */
static void read_add(read_scorer *scorer, th_node *node, double delta) {
    for (Py_ssize_t index = 0; index < scorer->count; index++) {
        if (scorer->candidates[index].node == node) {
            scorer->candidates[index].score += delta;
            return;
        }
    }
    if (scorer->count == scorer->cap) {
        Py_ssize_t grown = scorer->cap ? scorer->cap * 2 : READ_INITIAL_CANDIDATES;
        read_candidate *resized = PyMem_Realloc(scorer->candidates, (size_t)grown * sizeof(read_candidate));
        if (resized == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            return;            /* GCOVR_EXCL_LINE: allocation-failure path drops the candidate */
        }
        scorer->candidates = resized;
        scorer->cap = grown;
    }
    scorer->candidates[scorer->count].node = node;
    scorer->candidates[scorer->count].score = read_tag_base(node->atom) + read_class_weight(scorer->tree, node) + delta;
    scorer->count++;
}

/* Score one paragraph and propagate its contribution to the parent (full) and the
   grandparent (half), the candidates that compete to be the content root. */
static void read_score_paragraph(read_scorer *scorer, th_node *paragraph, th_node *parent, th_node *grandparent) {
    read_stats stats = {0, 0, 0};
    read_text_stats(scorer->tree, paragraph, 0, &stats);
    if (stats.chars < READ_MIN_PARAGRAPH_CHARS) {
        return;
    }
    Py_ssize_t length_bonus = stats.chars / 100;
    if (length_bonus > READ_CHAR_SCORE_CAP) {
        length_bonus = READ_CHAR_SCORE_CAP;
    }
    double contribution = 1.0 + (double)(stats.commas + 1) + (double)length_bonus;
    read_add(scorer, parent, contribution);
    if (grandparent != NULL) {
        read_add(scorer, grandparent, contribution / 2.0);
    }
}

/* Walk node's element children, scoring paragraphs against their parent (node, when
   it is an element) and grandparent (the nearest enclosing element above node). */
static void read_walk(read_scorer *scorer, th_node *node, th_node *grandparent) {
    int node_is_element = node->type == TH_NODE_ELEMENT;
    for (th_node *child = node->first_child; child != NULL; child = child->next_sibling) {
        if (child->type != TH_NODE_ELEMENT || read_should_skip(scorer->tree, child)) {
            continue;
        }
        if (node_is_element &&
            read_atom_in(child->atom, read_paragraph_tags, sizeof(read_paragraph_tags) / sizeof(uint16_t))) {
            read_score_paragraph(scorer, child, node, grandparent);
        }
        read_walk(scorer, child, node_is_element ? node : grandparent);
    }
}

/* The candidate with the highest score after each is discounted by its link
   density, or NULL when nothing scores positively. */
static th_node *read_best(read_scorer *scorer) {
    th_node *best = NULL;
    double best_score = 0;
    for (Py_ssize_t index = 0; index < scorer->count; index++) {
        double density = read_link_density(scorer->tree, scorer->candidates[index].node);
        double score = scorer->candidates[index].score * (1.0 - density);
        if (score > best_score) {
            best_score = score;
            best = scorer->candidates[index].node;
        }
    }
    return best;
}

/* The dominant content element under root by the readability content-density
   heuristic, or NULL when no element scores as content. Pure C; the caller holds
   the per-tree critical section and wraps (or renders) the result afterwards. */
th_node *th_node_main_content(th_tree *tree, th_node *root) {
    read_scorer scorer = {tree, NULL, 0, 0};
    read_walk(&scorer, root, NULL);
    th_node *best = read_best(&scorer);
    PyMem_Free(scorer.candidates);
    return best;
}
