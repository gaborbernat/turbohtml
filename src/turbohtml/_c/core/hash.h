/* Hashing of names that arrive in untrusted input.

   The tokenizer's per-tag duplicate-attribute index (tokenizer/statemachine.c), the tree's dynamic
   attribute-name table (dom/tree.c), and the string tables of XPath id() and translate(), xsl:key and
   minify_js are open-addressing tables with linear probing, keyed by text the document author picks.
   Linear probing stays O(1) only while home slots are spread over the table: a hash that can be
   evaluated offline lets a document choose names that land in one run of slots, and every further
   name then walks that run, the quadratic cost the tables exist to remove (CWE-407).

   Each of those tables starts on its own unkeyed hash, which is cheap, and watches the runs it builds.
   Once a run passes TH_FAST_PROBE_LIMIT the table rehashes its entries under th_name_hash (or
   th_key_mix for code points) and stays there. th_name_hash is SipHash-1-3 (Aumasson and Bernstein),
   the keyed hash CPython uses for str and bytes (PEP 456), under a 128-bit key the document cannot
   see, so the slots cannot be predicted from the input.

   th_name_hash is one out-of-line function in core/module.c: its rounds run only on keyed tables and
   long CSS rule bodies, and inlined at every call site they used up the link-time inliner's unit
   growth budget, which then dropped inlines on unrelated hot paths. */

#ifndef TURBOHTML_CORE_HASH_H
#define TURBOHTML_CORE_HASH_H

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdint.h>
#include <string.h>

#include "core/hash_limits.h"
#include "core/work_steps.h"

/* The 128-bit key, defined and set once per process in core/module.c. */
extern uint64_t th_name_hash_key[2];

/* SipHash-1-3 of `len` bytes under th_name_hash_key, truncated to the 32 bits the tables index by.
   Whole words are read in native byte order, since the value never leaves the process. Equal byte
   runs hash equal; the caller resolves a collision between distinct names by comparing them. */
uint32_t th_name_hash(const void *data, Py_ssize_t len);

/* FNV-1a over the bytes: the hash the name tables start on, since it costs a multiply per byte where
   th_name_hash costs its rounds. FNV-1a is fixed, so a document can still pick names that share one run of
   slots. Each table therefore watches its runs, and once one passes the limit the table rehashes its
   entries under th_name_hash for the rest of its life. Up to that point a probe walks at most the limit,
   and past it the key decides the slots, so a document can buy one bounded rehash and nothing quadratic. The
   limits are TH_FAST_PROBE_LIMIT and TH_FAST_RUN_LIMIT, in core/hash_limits.h. */

#ifndef TH_NOINLINE
#if defined(_MSC_VER)
#define TH_NOINLINE __declspec(noinline)
#elif defined(__GNUC__) || defined(__clang__)
#define TH_NOINLINE __attribute__((noinline))
#else
#define TH_NOINLINE
#endif
#endif

#if defined(__GNUC__) || defined(__clang__)
#define TH_UNLIKELY(cond) __builtin_expect(!!(cond), 0)
#else
#define TH_UNLIKELY(cond) (cond)
#endif

static inline uint32_t th_fnv1a_bytes(const void *data, Py_ssize_t len) {
    const unsigned char *bytes = data;
    uint32_t hash = 2166136261u;
    for (Py_ssize_t index = 0; index < len; index++) {
        hash = (hash ^ bytes[index]) * 16777619u;
    }
    return hash;
}

/* The splitmix64 finalizer of a fixed-width integer key (a code point, a packed trigram) under the same key, for the
   tables probed once per input character, where the rounds of th_name_hash would show. The key hides which integers
   share a slot. */
static inline uint64_t th_key_mix(uint64_t key) {
    uint64_t hash = key ^ th_name_hash_key[0];
    hash = (hash ^ (hash >> 30)) * UINT64_C(0xBF58476D1CE4E5B9);
    hash = (hash ^ (hash >> 27)) * UINT64_C(0x94D049BB133111EB);
    return hash ^ (hash >> 31);
}

/* Keyed name hashing in 8-byte blocks: each block is folded through a 64x64->128 multiply against secret-xored words
   (wyhash's mum step), with the per-process key in th_mix_key. Ordinary names cost one multiply per eight bytes, and no
   key-independent collision family exists for this shape. */
extern uint64_t th_mix_key[3];

static inline uint64_t th_mum(uint64_t a, uint64_t b) {
#if defined(__SIZEOF_INT128__)
    const unsigned __int128 product = (unsigned __int128)a * b;
    return (uint64_t)product ^ (uint64_t)(product >> 64);
#else
    const uint64_t a_lo = (uint32_t)a;
    const uint64_t a_hi = a >> 32;
    const uint64_t b_lo = (uint32_t)b;
    const uint64_t b_hi = b >> 32;
    const uint64_t lo_lo = a_lo * b_lo;
    const uint64_t hi_lo = a_hi * b_lo;
    const uint64_t lo_hi = a_lo * b_hi;
    const uint64_t hi_hi = a_hi * b_hi;
    const uint64_t cross = (lo_lo >> 32) + (uint32_t)hi_lo + lo_hi;
    const uint64_t high = (hi_lo >> 32) + (cross >> 32) + hi_hi;
    const uint64_t low = (cross << 32) | (uint32_t)lo_lo;
    return low ^ high;
#endif
}

typedef struct {
    uint64_t state;
    uint64_t word;
    uint64_t length;
    unsigned fill;
} th_mix_stream;

static inline void th_mix_stream_init(th_mix_stream *stream, uint64_t seed) {
    stream->state = seed;
    stream->word = 0;
    stream->length = 0;
    stream->fill = 0;
}

static inline void th_mix_stream_byte(th_mix_stream *stream, uint64_t byte) {
    stream->word |= (byte & 0xFFu) << (8 * stream->fill);
    stream->length++;
    if (++stream->fill == 8) {
        stream->state = th_mum(stream->state ^ stream->word, th_mix_key[0]);
        stream->word = 0;
        stream->fill = 0;
    }
}

static inline void th_mix_stream_unit(th_mix_stream *stream, uint64_t unit) {
    for (unsigned shift = 0; shift < 32; shift += 8) {
        th_mix_stream_byte(stream, unit >> shift);
    }
}

static inline void th_mix_stream_word(th_mix_stream *stream, uint64_t word) {
    for (unsigned shift = 0; shift < 64; shift += 8) {
        th_mix_stream_byte(stream, word >> shift);
    }
}

static inline uint64_t th_mix_stream_finish(const th_mix_stream *stream) {
    const uint64_t state = th_mum(stream->state ^ stream->word, th_mix_key[1]);
    return th_mum(state ^ th_mix_key[2], stream->length ^ th_mix_key[1]);
}

static inline uint64_t th_mix_word(uint64_t state, uint64_t word) {
    return th_mum(state ^ word, th_mix_key[0]);
}

static inline uint64_t th_mix_finish(uint64_t state, uint64_t length) {
    return th_mum(state ^ th_mix_key[2], length ^ th_mix_key[1]);
}

/* ASCII characters hashed as the bytes of their UTF-8 encoding: th_mix_bytes of the same name, without the narrowing.
 */
static inline uint64_t th_mix_ucs4_ascii(uint64_t seed, const uint32_t *chars, Py_ssize_t len) {
    uint64_t state = seed;
    Py_ssize_t index = 0;
    for (; index + 8 <= len; index += 8) {
        uint64_t word = 0;
        for (int at = 7; at >= 0; at--) {
            word = (word << 8) | chars[index + at];
        }
        state = th_mix_word(state, word);
    }
    uint64_t tail = 0;
    for (Py_ssize_t at = 0; index + at < len; at++) {
        tail |= (uint64_t)chars[index + at] << (8 * at);
    }
    state = th_mum(state ^ tail, th_mix_key[1]);
    return th_mix_finish(state, (uint64_t)len);
}

/* Units of 32 bits, two to a block: the hash of a code point array, continuing from seed. */
static inline uint64_t th_mix_u32s(uint64_t seed, const uint32_t *units, Py_ssize_t len) {
    uint64_t state = seed;
    Py_ssize_t index = 0;
    for (; index + 2 <= len; index += 2) {
        state = th_mix_word(state, (uint64_t)units[index] | ((uint64_t)units[index + 1] << 32));
    }
    const uint64_t tail = index < len ? units[index] : 0;
    state = th_mum(state ^ tail, th_mix_key[1]);
    return th_mix_finish(state, (uint64_t)len);
}

static inline uint64_t th_mix_bytes(uint64_t seed, const void *data, Py_ssize_t len) {
    const unsigned char *bytes = data;
    uint64_t state = seed;
    Py_ssize_t index = 0;
    for (; index + 8 <= len; index += 8) {
        uint64_t word = 0;
        for (int at = 7; at >= 0; at--) {
            word = (word << 8) | bytes[index + at];
        }
        state = th_mum(state ^ word, th_mix_key[0]);
    }
    uint64_t tail = 0;
    for (Py_ssize_t at = 0; index + at < len; at++) {
        tail |= (uint64_t)bytes[index + at] << (8 * at);
    }
    state = th_mum(state ^ tail, th_mix_key[1]);
    return th_mum(state ^ th_mix_key[2], (uint64_t)len ^ th_mix_key[1]);
}

#endif /* TURBOHTML_CORE_HASH_H */
