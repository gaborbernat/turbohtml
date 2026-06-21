/* Tree-builder internals shared between the parser (tree.c) and the standalone
   serialization translation units. The arena, the borrowed-input readers, the
   lazy text-span realization and the void-element predicate live here as
   `static inline` so every including unit keeps its own inlined copy — the
   serialize hot path pays no cross-TU call for need_text() or is_void_atom(). */

#ifndef TURBOHTML_DOM_TREE_INTERNAL_H
#define TURBOHTML_DOM_TREE_INTERNAL_H

#include "dom/tree.h"

#include <string.h>

/* --------------------------------------------------------------- arena */

#define ARENA_BLOCK ((Py_ssize_t)64 * 1024)

typedef struct arena_block {
    struct arena_block *next;
    Py_ssize_t used;
    Py_ssize_t cap;
    char data[];
} arena_block;

/* One interned dynamic attribute name (a name outside the static attr_atom.h
   table). The bytes are arena-owned UTF-8, NUL-terminated. */
typedef struct {
    const char *name;
    uint32_t name_len;
    uint32_t hash;
} th_attr_record;

struct th_tree {
    arena_block *arena;
    th_node *document;
    th_node **open; /* stack of open elements */
    Py_ssize_t open_len;
    Py_ssize_t open_cap;
    th_node **afe; /* active formatting elements; NULL entry is a scope marker */
    Py_ssize_t afe_len;
    Py_ssize_t afe_cap;
    th_node *head;          /* the <head> element once inserted */
    th_node *fragment_root; /* the html root in fragment parsing; NULL otherwise */
    uint16_t ctx_atom;      /* the fragment context element's atom (reset uses it) */
    th_node *form;          /* the form element pointer: nested forms are ignored */
    int *tmpl;              /* stack of template insertion modes (enum mode as int) */
    Py_ssize_t tmpl_len;
    Py_ssize_t tmpl_cap;
    int frameset_ok;        /* a <frameset> may still replace an empty body */
    int drop_newline;       /* drop a single leading LF after pre/listing/textarea */
    Py_ssize_t text_offset; /* leading code points of a reprocessed text token already consumed */
    int foster;             /* when set, inserts are foster-parented out of a table */
    int quirks;             /* quirks mode: a <table> no longer closes an open <p> */
    int has_nul;            /* the input contains a U+0000; otherwise text needs no NUL filtering */
    int can_span;           /* input is borrowed and outlives the tree: text nodes may be
                               zero-copy spans into it instead of materialized copies */
    int track_positions;    /* record each element's source line/col in trailing node slots */
    int kind;               /* borrowed input storage */
    const void *data;
    Py_ssize_t length;
    int failed; /* an allocation failed; abandon the parse */
    /* Dynamic intern table for attribute names outside attr_atom.h: the record
       for atom d is attr_recs[d - TH_ATTR__DYNAMIC_BASE]; attr_slots maps a name
       hash to its record. Grown only as uncommon names appear; read-only after
       the parse, so no lock is needed under the free-threaded build. */
    th_attr_record *attr_recs;
    uint32_t attr_rec_count;
    uint32_t attr_rec_cap;
    uint32_t *attr_slots; /* slot -> record index + 1; 0 marks an empty slot */
    uint32_t attr_slot_mask;
    /* WHATWG parse errors collected during the parse, in document order. The
       tokenizer fills it through this sink while the tree builder adds its own
       construction errors; read-only once the parse returns. */
    th_error_sink errors;
};

static inline void *arena_alloc(th_tree *tree, Py_ssize_t size) {
    size = (size + 15) & ~(Py_ssize_t)15; /* 16-byte align */
    arena_block *block = tree->arena;
    if (block == NULL || block->used + size > block->cap) {
        Py_ssize_t cap = size > ARENA_BLOCK ? size : ARENA_BLOCK;
        arena_block *fresh = PyMem_Malloc(sizeof(arena_block) + (size_t)cap);
        if (fresh == NULL) {  /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
            tree->failed = 1; /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
            return NULL;      /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
        }
        fresh->next = tree->arena;
        fresh->used = 0;
        fresh->cap = cap;
        tree->arena = fresh;
        block = fresh;
    }
    void *result = block->data + block->used;
    block->used += size;
    return result;
}

/* Copy the input span [off, off+length) into a freshly arena-allocated UCS4
   array, widening the borrowed input to code points. Shared by slice
   materialization and the lazy realization of zero-copy text spans. */
static inline Py_UCS4 *copy_input_span(th_tree *tree, Py_ssize_t off, Py_ssize_t length) {
    Py_UCS4 *out = arena_alloc(tree, length * (Py_ssize_t)sizeof(Py_UCS4));
    if (out == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;   /* GCOVR_EXCL_LINE: allocation-failure path, unreachable from a test */
    }
    if (tree->kind == PyUnicode_4BYTE_KIND) {
        memcpy(out, (const Py_UCS4 *)tree->data + off, (size_t)length * sizeof(Py_UCS4));
    } else if (tree->kind == PyUnicode_1BYTE_KIND) {
        const uint8_t *bytes = (const uint8_t *)tree->data + off;
        for (Py_ssize_t index = 0; index < length; index++) {
            out[index] = bytes[index];
        }
    } else {
        const uint16_t *units = (const uint16_t *)tree->data + off;
        for (Py_ssize_t index = 0; index < length; index++) {
            out[index] = units[index];
        }
    }
    return out;
}

/* A TEXT node is a zero-copy span when text == NULL && text_len > 0: its content
   is input[attr_count .. attr_count + text_len] (the attr_count field is unused
   on text nodes). Realize it into the arena on first read. */
static inline Py_UCS4 *need_text(th_tree *tree, th_node *node) {
    if (node->text == NULL && node->text_len > 0) { /* GCOVR_EXCL_BR_LINE: a text span always has positive length */
        node->text = copy_input_span(tree, node->attr_count, node->text_len);
    }
    return node->text;
}

static inline int is_void_atom(uint16_t atom) {
    switch (atom) {
    case TH_TAG_AREA:
    case TH_TAG_BASE:
    case TH_TAG_BASEFONT:
    case TH_TAG_BGSOUND:
    case TH_TAG_BR:
    case TH_TAG_COL:
    case TH_TAG_EMBED:
    case TH_TAG_HR:
    case TH_TAG_IMG:
    case TH_TAG_INPUT:
    case TH_TAG_KEYGEN:
    case TH_TAG_LINK:
    case TH_TAG_META:
    case TH_TAG_PARAM:
    case TH_TAG_SOURCE:
    case TH_TAG_TRACK:
    case TH_TAG_WBR:
        return 1;
    default:
        return 0;
    }
}

#endif /* TURBOHTML_DOM_TREE_INTERNAL_H */
