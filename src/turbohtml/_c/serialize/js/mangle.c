/* Identifier mangling: rename local bindings to short names.

   A post-parse pass over the arena AST. It builds the lexical scope tree, declares
   every binding, resolves every identifier reference to its binding (or to a free /
   global name), then assigns the shortest legal names to the locals.

   Correctness is by construction and conservative - under-renaming is safe, only a
   wrong rename corrupts:
   - A scope reached by `with` or a direct `eval(` is poisoned; nothing inside it (or
     any enclosing scope) is renamed, because those constructs resolve names
     dynamically.
   - Every free / global name used anywhere in the program is forbidden as a new
     name, so a binding can never be renamed onto a name that some reference resolves
     to globally - even a reference this pass failed to resolve keeps its (free) name
     and that name is reserved.
   - A new name also avoids every reserved word and every enclosing binding's name in
     scope, so it can neither be a keyword nor shadow an outer binding that is visible.
   Naming runs in two steps: each binding gets a slot index (inherited down the scope
   tree so a nested binding never shares a slot with a visible ancestor, while disjoint
   sibling scopes reuse slots), then the shortest names go to the slots whose bindings
   are referenced most -- the frequency ordering esbuild/terser/swc use. */

#include "serialize/js/internal.h"

#include <stdlib.h>
#include <string.h>

static int name_eq(const Py_UCS4 *left, Py_ssize_t left_len, const Py_UCS4 *right, Py_ssize_t right_len) {
    if (left_len != right_len) {
        return 0;
    }
    return memcmp(left, right, (size_t)left_len * sizeof(Py_UCS4)) == 0;
}

/* ----------------------------------------------------------- name hash table

   An open-addressing (linear-probe) map from an identifier name to an int32 value.
   Used three ways: the visible-binding map (value = symbol index, or -1 when the
   binding it held has gone out of scope), the free-name set, and the enclosing-binding
   set during renaming (value = 1 for present). A slot is never deleted; going out of
   scope just resets the value, so probe chains stay intact and scope exit is an O(1)
   restore from an undo log. */
typedef struct {
    const Py_UCS4 *name;
    Py_ssize_t len;
    int32_t val;
} hslot;

typedef struct {
    hslot *slots;
    int32_t cap; /* a power of two */
    int32_t count;
    int failed;
} htab;

static uint32_t name_hash(const Py_UCS4 *name, Py_ssize_t len) {
    uint32_t hash = 2166136261u;
    for (Py_ssize_t index = 0; index < len; index++) {
        hash = (hash ^ (uint32_t)name[index]) * 16777619u;
    }
    return hash;
}

static void htab_resize(htab *table, int32_t cap) {
    hslot *slots = jm_calloc((size_t)cap, sizeof(hslot));
    if (slots == NULL) {   /* GCOVR_EXCL_BR_LINE: allocation-failure path */
        table->failed = 1; /* GCOVR_EXCL_LINE */
        return;            /* GCOVR_EXCL_LINE */
    }
    uint32_t mask = (uint32_t)cap - 1;
    for (int32_t index = 0; index < table->cap; index++) {
        if (table->slots[index].name != NULL) {
            uint32_t probe = name_hash(table->slots[index].name, table->slots[index].len) & mask;
            while (slots[probe].name != NULL) {
                probe = (probe + 1) & mask;
            }
            slots[probe] = table->slots[index];
        }
    }
    jm_free(table->slots);
    table->slots = slots;
    table->cap = cap;
}

/* Find the slot for name; with create, claim an empty slot (value -1) and grow the
   table when it passes a 3/4 load. Returns NULL only when create is 0 and absent, or
   on allocation failure. */
static hslot *htab_slot(htab *table, const Py_UCS4 *name, Py_ssize_t len, int create) {
    if (create && (table->cap == 0 || (table->count + 1) * 4 >= table->cap * 3)) {
        htab_resize(table, table->cap ? table->cap * 2 : 64);
        if (table->failed) { /* GCOVR_EXCL_BR_LINE: allocation-failure path */
            return NULL;     /* GCOVR_EXCL_LINE */
        }
    }
    if (table->cap == 0) {
        return NULL; /* an empty read-only table */
    }
    uint32_t mask = (uint32_t)table->cap - 1;
    uint32_t probe = name_hash(name, len) & mask;
    for (;;) {
        hslot *slot = &table->slots[probe];
        if (slot->name == NULL) {
            if (!create) {
                return NULL;
            }
            slot->name = name;
            slot->len = len;
            slot->val = -1;
            table->count++;
            return slot;
        }
        if (name_eq(slot->name, slot->len, name, len)) {
            return slot;
        }
        probe = (probe + 1) & mask;
    }
}

/* ----------------------------------------------------------- reserved words */

static int is_reserved(const Py_UCS4 *name, Py_ssize_t len) {
    static const char *const words[] = {
        "break",   "case",   "catch",  "class",      "const",   "continue",   "debugger", "default",   "delete",
        "do",      "else",   "enum",   "export",     "extends", "false",      "finally",  "for",       "function",
        "if",      "import", "in",     "instanceof", "new",     "null",       "return",   "super",     "switch",
        "this",    "throw",  "true",   "try",        "typeof",  "var",        "void",     "while",     "with",
        "yield",   "let",    "static", "await",      "async",   "implements", "package",  "protected", "interface",
        "private", "public", "do",     NULL};
    for (int index = 0; words[index] != NULL; index++) {
        Py_ssize_t wlen = (Py_ssize_t)strlen(words[index]);
        if (wlen != len) {
            continue;
        }
        int same = 1;
        for (Py_ssize_t pos = 0; pos < len; pos++) {
            if (name[pos] != (Py_UCS4)(unsigned char)words[index][pos]) {
                same = 0;
                break;
            }
        }
        if (same) {
            return 1;
        }
    }
    return 0;
}

/* ----------------------------------------------------------- base54 names */

/* The i-th shortest identifier name: a bijective base-54-then-64 numeral. The first
   character comes from 54 options (no digit, identifiers cannot start with one); the
   rest from 64. PyMem-owned. */
static Py_UCS4 *base54(Py_ssize_t index, Py_ssize_t *out_len) {
    static const char head[] = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$";
    static const char tail[] = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$0123456789";
    Py_UCS4 buf[16];
    Py_ssize_t len = 0;
    Py_ssize_t value = index;
    buf[len++] = (Py_UCS4)(unsigned char)head[value % 54];
    value /= 54;
    while (value > 0) {
        value--;
        buf[len++] = (Py_UCS4)(unsigned char)tail[value % 64];
        value /= 64;
    }
    Py_UCS4 *name = jm_malloc((size_t)len * sizeof(Py_UCS4));
    if (name == NULL) { /* GCOVR_EXCL_BR_LINE: allocation-failure path */
        return NULL;    /* GCOVR_EXCL_LINE */
    }
    memcpy(name, buf, (size_t)len * sizeof(Py_UCS4));
    *out_len = len;
    return name;
}

/* ----------------------------------------------------------- analysis state

   Resolution uses one visible-binding table (name -> innermost visible symbol) rather
   than a per-reference walk up the scope chain. Entering a scope pushes its bindings,
   shadowing whatever they hide; leaving it restores them from the undo log. Each entry
   records the table, the name and the value to put back, so a single linear scan of the
   log unwinds a scope in O(bindings), and resolve is a single O(1) hash lookup. */
typedef struct {
    htab *table;
    const Py_UCS4 *name;
    Py_ssize_t len;
    int32_t old;
} undo_rec;

typedef struct {
    jm_program *prog;
    htab visible; /* name -> currently-visible symbol index (-1 when its binding is gone) */
    htab frees;   /* free / global names, plus kept declaration names, reserved (value 1) */
    htab labels;  /* label name -> its symbol (a separate namespace; -1 when kept verbatim) */
    undo_rec *undo;
    int32_t undo_count;
    int32_t undo_cap;
    int32_t slot_count;  /* number of distinct rename slots assigned across the program */
    int32_t global;      /* the global scope, where label symbols are parked */
    int32_t label_depth; /* count of lexically-enclosing labels, indexing their short names */
    int poisoned;        /* a with / eval was seen: stop renaming entirely */
    int failed;
} M;

static int32_t htab_get(htab *table, const Py_UCS4 *name, Py_ssize_t len) {
    hslot *slot = htab_slot(table, name, len, 0);
    return slot != NULL ? slot->val : -1;
}

/* Record, then apply, a shadowing assignment so a later undo_to can restore it. */
static void push(M *mangler, htab *table, const Py_UCS4 *name, Py_ssize_t len, int32_t val) {
    hslot *slot = htab_slot(table, name, len, 1);
    if (slot == NULL || table->failed) { /* GCOVR_EXCL_BR_LINE: allocation-failure path */
        mangler->failed = 1;             /* GCOVR_EXCL_LINE */
        return;                          /* GCOVR_EXCL_LINE */
    }
    if (mangler->undo_count == mangler->undo_cap) {
        int32_t cap = mangler->undo_cap ? mangler->undo_cap * 2 : 256;
        undo_rec *grown = jm_realloc(mangler->undo, (size_t)cap * sizeof(undo_rec));
        if (grown == NULL) {     /* GCOVR_EXCL_BR_LINE: allocation-failure path */
            mangler->failed = 1; /* GCOVR_EXCL_LINE */
            return;              /* GCOVR_EXCL_LINE */
        }
        mangler->undo = grown;
        mangler->undo_cap = cap;
    }
    mangler->undo[mangler->undo_count].table = table;
    mangler->undo[mangler->undo_count].name = name;
    mangler->undo[mangler->undo_count].len = len;
    mangler->undo[mangler->undo_count].old = slot->val;
    mangler->undo_count++;
    slot->val = val;
}

/* Unwind the undo log back to mark, restoring each shadowed binding. The name re-lookup
   is O(1) and stays correct even if the table was resized after the entry was pushed. */
static void undo_to(M *mangler, int32_t mark) {
    while (mangler->undo_count > mark) {
        mangler->undo_count--;
        undo_rec *rec = &mangler->undo[mangler->undo_count];
        hslot *slot = htab_slot(rec->table, rec->name, rec->len, 0);
        slot->val = rec->old; /* the slot always exists: push created it */
    }
}

/* Resolve a name to the innermost visible binding, or -1 (free / global). */
static int32_t resolve(M *mangler, const Py_UCS4 *name, Py_ssize_t len) {
    return htab_get(&mangler->visible, name, len);
}

static void declare(M *mangler, int32_t scope, const Py_UCS4 *name, Py_ssize_t len, uint8_t decl) {
    hslot *slot = htab_slot(&mangler->visible, name, len, 1);
    if (slot == NULL || mangler->visible.failed) { /* GCOVR_EXCL_BR_LINE: allocation-failure path */
        mangler->failed = 1;                       /* GCOVR_EXCL_LINE */
        return;                                    /* GCOVR_EXCL_LINE */
    }
    if (slot->val >= 0 && mangler->prog->syms[slot->val].scope == scope) {
        return; /* a re-declaration (var x; var x) reuses the same-scope symbol */
    }
    int32_t sym = jm_sym_new(mangler->prog, name, len, scope, decl);
    if (sym < 0) {           /* GCOVR_EXCL_BR_LINE: allocation-failure path */
        mangler->failed = 1; /* GCOVR_EXCL_LINE */
        return;              /* GCOVR_EXCL_LINE */
    }
    push(mangler, &mangler->visible, name, len, sym);
}

/* ----------------------------------------------------------- declaration walk */

static void declare_pattern(M *mangler, int32_t idx, int32_t scope, uint8_t decl);
static void hoist_vars(M *mangler, int32_t idx, int32_t fn_scope);

/* Declare the binding identifiers in a destructuring (or simple) target. */
static void declare_pattern(M *mangler, int32_t idx, int32_t scope, uint8_t decl) {
    jm_node *node = &mangler->prog->nodes[idx];
    switch (node->kind) {
    case JN_IDENT:
        declare(mangler, scope, node->str, node->str_len, decl);
        break;
    case JN_ARRAY:
        for (int32_t element = node->a; element >= 0; element = mangler->prog->nodes[element].next) {
            declare_pattern(mangler, element, scope, decl);
        }
        break;
    case JN_OBJECT:
        for (int32_t prop = node->a; prop >= 0; prop = mangler->prog->nodes[prop].next) {
            jm_node *pn = &mangler->prog->nodes[prop];
            declare_pattern(mangler, pn->kind == JN_SPREAD ? pn->a : pn->b >= 0 ? pn->b : pn->a, scope, decl);
        }
        break;
    case JN_ASSIGN: /* a default `target = init`, or a rest `...target` */
    case JN_SPREAD:
        declare_pattern(mangler, node->a, scope, decl);
        break;
    default:
        break;
    }
}

/* Hoist every `var` (and var-style for-loop binding) in the subtree to fn_scope,
   without descending into nested function bodies (which start their own var scope). */
static void hoist_vars(M *mangler, int32_t idx, int32_t fn_scope) {
    while (idx >= 0) {
        jm_node *node = &mangler->prog->nodes[idx];
        switch (node->kind) {
        case JN_FUNC:
        case JN_ARROW:
            break; /* a nested function has its own var scope */
        case JN_VAR:
            if (node->decl == 0) {
                for (int32_t declarator = node->a; declarator >= 0;
                     declarator = mangler->prog->nodes[declarator].next) {
                    declare_pattern(mangler, mangler->prog->nodes[declarator].a, fn_scope, 0);
                }
            }
            break;
        case JN_FORIN:
        case JN_FOROF:
            if (mangler->prog->nodes[node->a].kind == JN_VAR && mangler->prog->nodes[node->a].decl == 0) {
                hoist_vars(mangler, node->a, fn_scope);
            }
            hoist_vars(mangler, node->c, fn_scope);
            break;
        default:
            /* descend into every child to find vars through blocks, if, for, ... */
            hoist_vars(mangler, node->a, fn_scope);
            hoist_vars(mangler, node->b, fn_scope);
            hoist_vars(mangler, node->c, fn_scope);
            hoist_vars(mangler, node->d, fn_scope);
            break;
        }
        idx = node->next;
    }
}

/* Declare the block-level bindings (let/const, function and class declarations) that
   appear directly among stmts, in scope. */
static void hoist_block(M *mangler, int32_t first, int32_t scope) {
    for (int32_t idx = first; idx >= 0; idx = mangler->prog->nodes[idx].next) {
        jm_node *node = &mangler->prog->nodes[idx];
        if (node->kind == JN_VAR && node->decl != 0) {
            for (int32_t declarator = node->a; declarator >= 0; declarator = mangler->prog->nodes[declarator].next) {
                declare_pattern(mangler, mangler->prog->nodes[declarator].a, scope, node->decl);
            }
        } else if (node->kind == JN_FUNC) { /* in a statement list a function is always a named declaration */
            declare(mangler, scope, node->str, node->str_len, 4);
            node->sym = resolve(mangler, node->str, node->str_len); /* so the name renames with its references */
            if (node->sym >= 0) { /* GCOVR_EXCL_BR_LINE: unresolved only on an allocation failure */
                mangler->prog->syms[node->sym].decl_node = idx; /* let drop_unused find an unused function */
            }
        } else if (node->kind == JN_CLASS) { /* likewise a class is always a named declaration */
            declare(mangler, scope, node->str, node->str_len, 6);
            node->sym = resolve(mangler, node->str, node->str_len);
        }
    }
}

/* ----------------------------------------------------------- resolve walk */

static void walk(M *mangler, int32_t idx, int32_t scope, int bind);

/* Walk a chain of siblings. */
static void walk_chain(M *mangler, int32_t first, int32_t scope, int bind) {
    for (int32_t idx = first; idx >= 0; idx = mangler->prog->nodes[idx].next) {
        walk(mangler, idx, scope, bind);
    }
}

/* Open a function/arrow scope: declare params + hoisted bindings, then walk the body. */
static void walk_function(M *mangler, int32_t idx, int32_t parent) {
    jm_node *node = &mangler->prog->nodes[idx];
    int32_t scope = jm_scope_new(mangler->prog, parent, 1);
    if (scope < 0) {         /* GCOVR_EXCL_BR_LINE: allocation-failure path */
        mangler->failed = 1; /* GCOVR_EXCL_LINE */
        return;              /* GCOVR_EXCL_LINE */
    }
    int32_t mark = mangler->undo_count;
    /* a named function expression binds its own name inside its scope (and nowhere else), so the
       name is renamable (decl 7) like any local; tag the node so the printer emits the new name */
    if (node->kind == JN_FUNC && (node->flags & JN_F_EXPR) && node->str != NULL) {
        declare(mangler, scope, node->str, node->str_len, 7);
        node->sym = resolve(mangler, node->str, node->str_len);
    }
    for (int32_t param = node->a; param >= 0; param = mangler->prog->nodes[param].next) {
        declare_pattern(mangler, param, scope, 3);
    }
    int32_t body = node->b;
    if (node->kind == JN_ARROW && (node->flags & JN_F_EXPRBODY)) {
        /* default param values reference the param scope, then the expression body */
        walk_chain(mangler, node->a, scope, 1);
        walk(mangler, body, scope, 0);
        undo_to(mangler, mark);
        return;
    }
    /* params may carry default-value expressions and patterns */
    walk_chain(mangler, node->a, scope, 1);
    int32_t body_stmts = mangler->prog->nodes[body].a;
    hoist_vars(mangler, body_stmts, scope);
    hoist_block(mangler, body_stmts, scope);
    walk_chain(mangler, body_stmts, scope, 0);
    undo_to(mangler, mark);
}

/* Walk node idx in scope. bind selects how an identifier is counted: 0 a read reference, 1 a
   declaration target (already declared, only resolved here), 2 an assignment/update/for-in write
   target. The read/write split lets the inline and dead-binding passes tell a value's reads from its
   reassignments. */
static void walk(M *mangler, int32_t idx, int32_t scope, int bind) {
    if (idx < 0) {
        return;
    }
    jm_node *node = &mangler->prog->nodes[idx];
    switch (node->kind) {
    case JN_IDENT: {
        int32_t sym = resolve(mangler, node->str, node->str_len);
        node->sym = sym;
        if (sym >= 0) {
            mangler->prog->syms[sym].uses++;
            if (bind == 0) { /* a read reference */
                mangler->prog->syms[sym].refs++;
                mangler->prog->syms[sym].ref_node = idx;
            } else if (bind == 2) { /* an assignment / update / for-in target: a write */
                mangler->prog->syms[sym].writes++;
            } /* bind == 1: a declaration target, neither read nor write */
        } else {
            hslot *slot = htab_slot(&mangler->frees, node->str, node->str_len, 1); /* a global / free name */
            if (slot != NULL) { /* GCOVR_EXCL_BR_LINE: the false branch is an allocation failure */
                slot->val = 1;
            }
        }
        return;
    }
    case JN_FUNC:
    case JN_ARROW:
        walk_function(mangler, idx, scope);
        return;
    case JN_BLOCK: {
        int32_t inner = jm_scope_new(mangler->prog, scope, 0);
        if (inner < 0) {         /* GCOVR_EXCL_BR_LINE: allocation-failure path */
            mangler->failed = 1; /* GCOVR_EXCL_LINE */
            return;              /* GCOVR_EXCL_LINE */
        }
        int32_t mark = mangler->undo_count;
        hoist_block(mangler, node->a, inner);
        walk_chain(mangler, node->a, inner, 0);
        undo_to(mangler, mark);
        return;
    }
    case JN_FOR:
    case JN_FORIN:
    case JN_FOROF: {
        /* a let/const loop binding scopes to the loop; give the whole loop a scope */
        int32_t inner = jm_scope_new(mangler->prog, scope, 0);
        if (inner < 0) {         /* GCOVR_EXCL_BR_LINE: allocation-failure path */
            mangler->failed = 1; /* GCOVR_EXCL_LINE */
            return;              /* GCOVR_EXCL_LINE */
        }
        int32_t mark = mangler->undo_count;
        if (node->kind == JN_FOR) {
            if (node->a >= 0 && mangler->prog->nodes[node->a].kind == JN_VAR &&
                mangler->prog->nodes[node->a].decl != 0) {
                hoist_block(mangler, node->a, inner);
            }
            walk(mangler, node->a, inner, 0);
            walk(mangler, node->b, inner, 0);
            walk(mangler, node->c, inner, 0);
            walk(mangler, node->d, inner, 0);
        } else {
            if (mangler->prog->nodes[node->a].kind == JN_VAR && mangler->prog->nodes[node->a].decl != 0) {
                hoist_block(mangler, node->a, inner);
            }
            /* `for(var x in o)` declares x; `for(x in o)` assigns it -- a write target */
            walk(mangler, node->a, inner, mangler->prog->nodes[node->a].kind == JN_VAR ? 0 : 2);
            walk(mangler, node->b, inner, 0);
            walk(mangler, node->c, inner, 0);
            /* a for-in/for-of loop binding is required syntax (`for( in o)` is invalid), so it is never
               a drop or inline candidate: forget the single-ident declaration the JN_VAR walk recorded
               (a destructuring target was never recorded, so it needs no clearing) */
            if (mangler->prog->nodes[node->a].kind == JN_VAR) {
                int32_t bound = mangler->prog->nodes[mangler->prog->nodes[node->a].a].a;
                if (mangler->prog->nodes[bound].kind == JN_IDENT) {
                    int32_t bsym = mangler->prog->nodes[bound].sym;
                    if (bsym >= 0) { /* GCOVR_EXCL_BR_LINE: unresolved only on an allocation failure */
                        mangler->prog->syms[bsym].decl_node = -1;
                    }
                }
            }
        }
        undo_to(mangler, mark);
        return;
    }
    case JN_TRY:
        walk(mangler, node->a, scope, 0);
        if (node->c >= 0) {
            int32_t cat = jm_scope_new(mangler->prog, scope, 2);
            if (cat < 0) {           /* GCOVR_EXCL_BR_LINE: allocation-failure path */
                mangler->failed = 1; /* GCOVR_EXCL_LINE */
                return;              /* GCOVR_EXCL_LINE */
            }
            int32_t mark = mangler->undo_count;
            if (node->b >= 0) {
                declare_pattern(mangler, node->b, cat, 5);
                walk(mangler, node->b, cat, 1);
            }
            walk_chain(mangler, mangler->prog->nodes[node->c].a, cat, 0);
            undo_to(mangler, mark);
        }
        walk(mangler, node->d, scope, 0);
        return;
    case JN_VAR:
        for (int32_t declarator = node->a; declarator >= 0; declarator = mangler->prog->nodes[declarator].next) {
            walk(mangler, mangler->prog->nodes[declarator].a, scope, 1); /* resolve the (declared) target */
            walk(mangler, mangler->prog->nodes[declarator].b, scope, 0); /* the initializer is a reference context */
        }
        /* a lone `name = init` declaration (every JN_VAR is var/let/const) is a candidate for single-use
           inlining and for unused-binding elimination: record its statement so those passes can find and
           drop it. node->a is its one declarator, its target an ident. */
        if (mangler->prog->nodes[node->a].next < 0 &&
            mangler->prog->nodes[mangler->prog->nodes[node->a].a].kind == JN_IDENT) {
            int32_t target = mangler->prog->nodes[mangler->prog->nodes[node->a].a].sym;
            if (target >= 0) { /* GCOVR_EXCL_BR_LINE: unresolved only on a hoist allocation failure */
                mangler->prog->syms[target].decl_node = idx;
            }
        }
        return;
    case JN_MEMBER_EXPR:
        walk(mangler, node->a, scope, 0);
        if (node->flags & JN_F_COMPUTED) {
            walk(mangler, node->b, scope, 0); /* a[b]: b is a reference */
        }
        /* a.b: b is a property name, not a variable - skip */
        return;
    case JN_PROP:
        if (node->flags & JN_F_COMPUTED) {
            walk(mangler, node->a, scope, 0);
        }
        walk(mangler, node->b, scope, bind);
        if (node->flags & JN_F_SHORTHAND) {
            walk(mangler, node->a, scope, bind); /* { x } references (or binds) x */
        }
        return;
    case JN_MEMBER: /* class member: key may be computed; value is a function */
        if (node->flags & JN_F_COMPUTED) {
            walk(mangler, node->a, scope, 0);
        }
        walk(mangler, node->b, scope, 0);
        return;
    case JN_ARRAY:
    case JN_OBJECT:
    case JN_SEQ:
    case JN_TEMPLATE:
        walk_chain(mangler, node->a, scope, bind); /* elements / properties / exprs / parts */
        return;
    case JN_CALL: {
        /* a direct call to `eval` resolves names dynamically: poison renaming */
        const jm_node *callee = &mangler->prog->nodes[node->a];
        if (callee->kind == JN_IDENT && callee->str_len == 4 && callee->str[0] == 'e' && callee->str[1] == 'v' &&
            callee->str[2] == 'a' && callee->str[3] == 'l') {
            mangler->poisoned = 1;
        }
        walk(mangler, node->a, scope, 0);
        walk_chain(mangler, node->b, scope, 0);
        return;
    }
    case JN_NEW: /* a = callee, b = arguments */
        walk(mangler, node->a, scope, 0);
        walk_chain(mangler, node->b, scope, 0);
        return;
    case JN_CLASS: { /* a = superclass, b = members */
        /* a named class expression binds its own name inside the class body (heritage included)
           and nowhere else, so the name is renamable; a class declaration keeps its (hoisted)
           name. Give the expression its own scope holding the renamable self-name. */
        if ((node->flags & JN_F_EXPR) && node->str != NULL) {
            int32_t inner = jm_scope_new(mangler->prog, scope, 0);
            if (inner < 0) {         /* GCOVR_EXCL_BR_LINE: allocation-failure path */
                mangler->failed = 1; /* GCOVR_EXCL_LINE */
                return;              /* GCOVR_EXCL_LINE */
            }
            int32_t mark = mangler->undo_count;
            declare(mangler, inner, node->str, node->str_len, 7);
            node->sym = resolve(mangler, node->str, node->str_len);
            walk(mangler, node->a, inner, 0);
            walk_chain(mangler, node->b, inner, 0);
            undo_to(mangler, mark);
            return;
        }
        walk(mangler, node->a, scope, 0);
        walk_chain(mangler, node->b, scope, 0);
        return;
    }
    case JN_SWITCH: {
        int32_t inner = jm_scope_new(mangler->prog, scope, 0); /* case bodies may hold let/const */
        if (inner < 0) {                                       /* GCOVR_EXCL_BR_LINE: allocation-failure path */
            mangler->failed = 1;                               /* GCOVR_EXCL_LINE */
            return;                                            /* GCOVR_EXCL_LINE */
        }
        int32_t mark = mangler->undo_count;
        walk(mangler, node->a, scope, 0); /* discriminant is in the outer scope */
        for (int32_t clause = node->b; clause >= 0; clause = mangler->prog->nodes[clause].next) {
            hoist_block(mangler, mangler->prog->nodes[clause].b, inner);
        }
        for (int32_t clause = node->b; clause >= 0; clause = mangler->prog->nodes[clause].next) {
            walk(mangler, mangler->prog->nodes[clause].a, inner, 0); /* case test */
            walk_chain(mangler, mangler->prog->nodes[clause].b, inner, 0);
        }
        undo_to(mangler, mark);
        return;
    }
    case JN_WITH:
        mangler->poisoned = 1; /* with(obj) resolves names against obj at runtime */
        walk(mangler, node->a, scope, 0);
        walk(mangler, node->b, scope, 0);
        return;
    case JN_LABEL: {
        /* labels are their own namespace (a label and a variable may share a name) and are always
           statically resolved, so they rename safely even under poison. The n-th enclosing label
           takes the n-th single-letter name (none of which is a reserved word); past 52 the label
           is kept verbatim. Shadow any enclosing same-named label either way so an inner
           break/continue still resolves to this one. */
        int32_t mark = mangler->undo_count;
        int32_t sym = -1;
        if (mangler->label_depth < 52) {
            Py_ssize_t len = 0;
            Py_UCS4 *name = base54(mangler->label_depth, &len);
            if (name == NULL) {      /* GCOVR_EXCL_BR_LINE: allocation-failure path */
                mangler->failed = 1; /* GCOVR_EXCL_LINE */
                return;              /* GCOVR_EXCL_LINE */
            }
            sym = jm_sym_new(mangler->prog, node->str, node->str_len, mangler->global, 8);
            if (sym < 0) {           /* GCOVR_EXCL_BR_LINE: allocation-failure path */
                jm_free(name);       /* GCOVR_EXCL_LINE */
                mangler->failed = 1; /* GCOVR_EXCL_LINE */
                return;              /* GCOVR_EXCL_LINE */
            }
            mangler->prog->syms[sym].mangled = name;
            mangler->prog->syms[sym].mangled_len = len;
            node->sym = sym;
        }
        push(mangler, &mangler->labels, node->str, node->str_len, sym);
        mangler->label_depth++;
        walk(mangler, node->a, scope, bind);
        mangler->label_depth--;
        undo_to(mangler, mark);
        return;
    }
    case JN_BREAK:
    case JN_CONTINUE:
        if (node->str != NULL) { /* a labeled jump: point it at the (possibly renamed) label */
            node->sym = htab_get(&mangler->labels, node->str, node->str_len);
        }
        return;
    case JN_ASSIGN: {
        /* a simple `x = v` writes x; a compound `x op= v` reads x and writes it. A member or
           destructuring target is walked as an ordinary expression, where its bindings read. */
        int simple = node->op == JT_ASSIGN;
        walk(mangler, node->a, scope, simple ? 2 : 0);
        if (!simple && mangler->prog->nodes[node->a].kind == JN_IDENT) {
            int32_t target = mangler->prog->nodes[node->a].sym;
            if (target >= 0) {
                mangler->prog->syms[target].writes++;
            }
        }
        walk(mangler, node->b, scope, 0);
        return;
    }
    case JN_UPDATE: /* ++x / x-- reads the operand and writes it */
        walk(mangler, node->a, scope, 0);
        if (mangler->prog->nodes[node->a].kind == JN_IDENT) {
            int32_t target = mangler->prog->nodes[node->a].sym;
            if (target >= 0) {
                mangler->prog->syms[target].writes++;
            }
        }
        return;
    default:
        break;
    }
    walk(mangler, node->a, scope, bind);
    walk(mangler, node->b, scope, bind);
    walk(mangler, node->c, scope, bind);
    walk(mangler, node->d, scope, bind);
}

/* ----------------------------------------------------------- rename */

/* Whether name is a reserved word or a name that must not be reused: a free/global
   name, or a kept function/class declaration name (reserved globally so a mangled
   binding never shadows one). The free table holds both, so this is O(1). */
static int is_forbidden(M *mangler, const Py_UCS4 *name, Py_ssize_t len) {
    return is_reserved(name, len) || htab_get(&mangler->frees, name, len) > 0;
}

/* Give every renamable binding of scope (and, recursively, its children) a slot index.

   The slot counter is inherited from the enclosing scope: a nested scope starts where
   its parent stopped, so a binding here can never share a slot with a visible ancestor
   -- the parent's count already passed every ancestor binding. Sibling scopes do not
   nest, so each restarts from the same inherited base and shares the other's slots.
   Names are assigned to slots afterwards, by frequency, so the slot is just a position;
   bindings that share a slot (across disjoint scopes) end up with the same short name. */
static void assign_slots(M *mangler, int32_t scope, int32_t base) {
    int32_t counter = base;
    for (int32_t sym = mangler->prog->scopes[scope].first_sym; sym >= 0; sym = mangler->prog->syms[sym].scope_next) {
        if (mangler->prog->syms[sym].decl_node == -2) {
            continue; /* an inlined const has no declaration left to name */
        }
        if ((mangler->prog->syms[sym].decl == 4 || mangler->prog->syms[sym].decl == 6) &&
            mangler->prog->scopes[scope].kind != 1) {
            continue; /* a function/class declaration in a block keeps its name: renaming it would
                         miss the Annex-B B.3.3 hoisted copy in the enclosing function scope. One
                         directly in a function body (scope kind 1) has no such copy and renames. */
        }
        mangler->prog->syms[sym].slot = counter++;
    }
    if (counter > mangler->slot_count) {
        mangler->slot_count = counter;
    }
    for (int32_t child = mangler->prog->scopes[scope].first_child; child >= 0;
         child = mangler->prog->scopes[child].next_sibling) {
        assign_slots(mangler, child, counter);
    }
}

/* A slot paired with the total number of references the bindings sharing it make, so
   slots can be ordered most-used first. */
typedef struct {
    uint64_t uses;
    int32_t slot;
} slot_rank;

/* Order by descending use count, then ascending slot index for a deterministic tie
   break. */
static int cmp_slot_rank(const void *pa, const void *pb) {
    const slot_rank *left = pa;
    const slot_rank *right = pb;
    if (left->uses != right->uses) {
        return left->uses < right->uses ? 1 : -1;
    }
    return (left->slot > right->slot) - (left->slot < right->slot); /* branchless slot tie-break */
}

/* Hand the shortest names to the slots whose bindings are referenced most, the way
   esbuild/terser/swc do: total each slot's references, sort slots by that count, then
   walk the base-54 sequence (skipping reserved and free names) assigning names in rank
   order. Every binding sharing a slot then copies that slot's name. */
static void assign_names_by_frequency(M *mangler) {
    if (mangler->slot_count == 0) {
        return; /* nothing renamable */
    }
    jm_program *prog = mangler->prog;
    slot_rank *ranks = jm_calloc((size_t)mangler->slot_count, sizeof(slot_rank));
    Py_UCS4 **slot_name = jm_calloc((size_t)mangler->slot_count, sizeof(Py_UCS4 *));
    Py_ssize_t *slot_len = jm_calloc((size_t)mangler->slot_count, sizeof(Py_ssize_t));
    if (ranks == NULL || slot_name == NULL || slot_len == NULL) { /* GCOVR_EXCL_BR_LINE: allocation-failure path */
        mangler->failed = 1;                                      /* GCOVR_EXCL_LINE */
        goto done;                                                /* GCOVR_EXCL_LINE */
    }
    for (int32_t index = 0; index < mangler->slot_count; index++) {
        ranks[index].slot = index;
    }
    for (int32_t sym = 0; sym < prog->sym_count; sym++) {
        if (prog->syms[sym].slot >= 0) {
            ranks[prog->syms[sym].slot].uses += prog->syms[sym].uses;
        }
    }
    qsort(ranks, (size_t)mangler->slot_count, sizeof(slot_rank), cmp_slot_rank);
    Py_ssize_t counter = 0;
    for (int32_t rank = 0; rank < mangler->slot_count; rank++) {
        Py_ssize_t len = 0;
        Py_UCS4 *name = NULL;
        for (;;) {
            jm_free(name);
            name = base54(counter++, &len);
            if (name == NULL) {      /* GCOVR_EXCL_BR_LINE: allocation-failure path */
                mangler->failed = 1; /* GCOVR_EXCL_LINE */
                goto done;           /* GCOVR_EXCL_LINE */
            }
            if (is_forbidden(mangler, name, len)) {
                continue;
            }
            break;
        }
        slot_name[ranks[rank].slot] = name;
        slot_len[ranks[rank].slot] = len;
    }
    for (int32_t sym = 0; sym < prog->sym_count; sym++) {
        int32_t slot = prog->syms[sym].slot;
        if (slot < 0) {
            continue;
        }
        Py_UCS4 *copy = jm_malloc((size_t)slot_len[slot] * sizeof(Py_UCS4));
        if (copy == NULL) {      /* GCOVR_EXCL_BR_LINE: allocation failure */
            mangler->failed = 1; /* GCOVR_EXCL_LINE */
            goto done;           /* GCOVR_EXCL_LINE */
        }
        memcpy(copy, slot_name[slot], (size_t)slot_len[slot] * sizeof(Py_UCS4));
        prog->syms[sym].mangled = copy;
        prog->syms[sym].mangled_len = slot_len[slot];
    }
done:
    if (slot_name != NULL) { /* GCOVR_EXCL_BR_LINE: a NULL table is an allocation failure */
        for (int32_t index = 0; index < mangler->slot_count; index++) {
            jm_free(slot_name[index]);
        }
    }
    jm_free(slot_name);
    jm_free(slot_len);
    jm_free(ranks);
}

/* A const initializer safe to inline at the use site: a value with no side effects that cannot
   change between the declaration and the use -- a number, string or regex literal, or a folded
   true/false/undefined (`!0`/`!1`/`void 0`). An identifier or member access would not qualify. */
static int is_const_literal(jm_program *prog, int32_t idx) {
    switch (prog->nodes[idx].kind) {
    case JN_NUM:
    case JN_STRING:
    case JN_REGEX:
        return 1;
    case JN_UNARY:
        return prog->nodes[prog->nodes[idx].a].kind == JN_NUM;
    default:
        return 0;
    }
}

/* Whether an unused binding's initializer can be discarded along with it: it has no observable side
   effect, so dropping `var/let/const name = init` (when name is never read) changes nothing. A literal,
   a function/arrow expression and a unary over a pure operand (`void 0`, `!0`, `-1`) are pure. A call,
   member access, `new`, identifier read (a free name may throw ReferenceError) or anything else is
   conservatively kept -- the binding then stays rather than risk losing a side effect (ECMA-262 13.3,
   14.3.2 spell out that only the initializer evaluation is observable). */
static int is_droppable_init(jm_program *prog, int32_t init) {
    if (init < 0) {
        return 1; /* a bare `var x;` declares nothing observable */
    }
    switch (prog->nodes[init].kind) {
    case JN_NUM:
    case JN_STRING:
    case JN_REGEX:
    case JN_BIGINT:
    case JN_FUNC:
    case JN_ARROW:
        return 1;
    case JN_UNARY:
        return is_droppable_init(prog, prog->nodes[init].a);
    default:
        return 0;
    }
}

/* Drop a local binding that is never referenced (dead-code elimination, ECMA-262 has no observable
   effect for an unread binding). A function declaration is dropped whole; a single-declarator
   var/let/const is dropped when its initializer is side-effect-free. Confined to non-global scopes so a
   top-level (observable) name is never removed, and the whole pass is skipped under with/eval (the
   caller guards on poisoned), where a name may resolve dynamically. References are counted across
   nested scopes by the walk, so a binding captured by a closure has refs > 0 and is kept. */
static void drop_unused(jm_program *prog, int32_t global) {
    for (int32_t sym = 0; sym < prog->sym_count; sym++) {
        if (prog->syms[sym].refs != 0 || prog->syms[sym].writes != 0 || prog->syms[sym].decl_node < 0 ||
            prog->syms[sym].scope == global) {
            continue; /* a written binding (even if never read) keeps its declaration; see dead stores */
        }
        if (prog->syms[sym].decl == 4) { /* an unused function declaration: drop the whole statement */
            prog->nodes[prog->syms[sym].decl_node].kind = JN_EMPTY;
            prog->syms[sym].decl_node = -2;
        } else { /* a single-ident var/let/const (the only other kind decl_node is recorded for) */
            int32_t init = prog->nodes[prog->nodes[prog->syms[sym].decl_node].a].b;
            if (is_droppable_init(prog, init)) {
                prog->nodes[prog->syms[sym].decl_node].kind = JN_EMPTY;
                prog->syms[sym].decl_node = -2;
            }
        }
    }
}

/* Inline a single-declarator binding that is read exactly once into that one read and drop the
   declaration (ECMA-262 propagates the assigned value; the optimization just removes the name). The
   walk records exactly one read (`refs == 1`) and no writes (`writes == 0`), so the value the
   declaration assigns is the value that single read sees, and the read is a genuine read position --
   never an assignment or for-in target the inlined value would land on illegally. Two cases are sound:

     - a let/const initialized to a literal: the value is constant and the declaration dominates its use
       (block scope / TDZ), so the read takes that value wherever it sits, a nested closure included;

     - any binding whose declaration is immediately followed by `return x` / `throw x` (x being the one
       read): nothing executes between the declaration and the read and the read is not inside a
       closure, so moving the initializer onto the jump preserves both value and evaluation order even
       when the initializer has side effects. A `var` is inlined only this way, never anywhere-at-once:
       a `var` declaration may be conditional or captured, so only adjacency proves it dominates.

   The emptied declaration is removed from its statement chain by the next fold pass. */
static void inline_single_use(jm_program *prog, int32_t global) {
    for (int32_t sym = 0; sym < prog->sym_count; sym++) {
        if (prog->syms[sym].decl > 2 || prog->syms[sym].refs != 1 || prog->syms[sym].writes != 0 ||
            prog->syms[sym].decl_node < 0 || prog->syms[sym].scope == global) {
            continue; /* exactly one read and never written: the read sees the value the declaration sets */
        }
        int32_t init = prog->nodes[prog->nodes[prog->syms[sym].decl_node].a].b;
        if (init < 0) {
            continue; /* a bare `var x;` declares no value to propagate */
        }
        int32_t ref = prog->syms[sym].ref_node;
        if (!(prog->syms[sym].decl >= 1 && is_const_literal(prog, init))) {
            int32_t jump = prog->nodes[prog->syms[sym].decl_node].next; /* the statement right after the decl */
            if (jump < 0 || (prog->nodes[jump].kind != JN_RETURN && prog->nodes[jump].kind != JN_THROW) ||
                prog->nodes[jump].a != ref) {
                continue; /* not a literal let/const, and not an adjacent `return x` / `throw x` */
            }
        }
        int32_t next = prog->nodes[ref].next;
        prog->nodes[ref] = prog->nodes[init];
        prog->nodes[ref].next = next;
        prog->nodes[prog->syms[sym].decl_node].kind = JN_EMPTY;
        prog->syms[sym].decl_node = -2; /* mark inlined so assign_slots spends no name on it */
    }
}

void jm_mangle(jm_program *prog) {
    M mangler = {0};
    mangler.prog = prog;
    int32_t global = jm_scope_new(prog, -1, 1);
    if (global < 0) { /* GCOVR_EXCL_BR_LINE: allocation-failure path */
        return;       /* GCOVR_EXCL_LINE */
    }
    mangler.global = global;
    int32_t stmts = prog->nodes[prog->root].a;
    hoist_vars(&mangler, stmts, global);
    hoist_block(&mangler, stmts, global);
    walk_chain(&mangler, stmts, global, 0);

    /* top-level (global-scope) bindings are observable; never rename them, and skip the
       whole pass when a with/eval anywhere makes name resolution unsafe */
    if (!mangler.poisoned) {
        /* the three failed flags are only ever set on allocation failure */
        if (!mangler.failed && !mangler.visible.failed && !mangler.frees.failed) { /* GCOVR_EXCL_BR_LINE */
            drop_unused(prog, global);       /* remove dead bindings before naming spends slots on them */
            inline_single_use(prog, global); /* before naming, so an inlined binding consumes no short name */
            /* reserve every *kept* function/class declaration name globally so a mangled binding in
               any scope can never be assigned a name that shadows one. A declaration in a non-global
               function scope is renamed, not kept (see assign_slots), so it is not reserved. */
            for (int32_t sym = 0; sym < prog->sym_count; sym++) {
                if ((prog->syms[sym].decl == 4 || prog->syms[sym].decl == 6) &&
                    (prog->syms[sym].scope == global || prog->scopes[prog->syms[sym].scope].kind != 1)) {
                    hslot *slot = htab_slot(&mangler.frees, prog->syms[sym].name, prog->syms[sym].name_len, 1);
                    if (slot != NULL) { /* GCOVR_EXCL_BR_LINE: the false branch is an allocation failure */
                        slot->val = 1;
                    }
                }
            }
            for (int32_t child = prog->scopes[global].first_child; child >= 0;
                 child = prog->scopes[child].next_sibling) {
                assign_slots(&mangler, child, 0);
            }
            assign_names_by_frequency(&mangler);
        }
    }
    jm_free(mangler.visible.slots);
    jm_free(mangler.frees.slots);
    jm_free(mangler.labels.slots);
    jm_free(mangler.undo);
}
