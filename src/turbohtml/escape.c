/* HTML escaping.

   escape() scans 1-byte strings word-at-a-time (SWAR): it loads eight bytes
   into a uint64_t and tests every lane for a special character at once, so it
   skips eight safe bytes per step and returns the input unchanged when nothing
   needs escaping. UCS-2 / UCS-4 strings use a straightforward scalar scan. */

#include "turbohtml.h"

#include <stdint.h>
#include <string.h>

#define SWAR_ONES 0x0101010101010101ULL
#define SWAR_HIGHS 0x8080808080808080ULL

static inline uint64_t swar_haszero(uint64_t v) {
    return (v - SWAR_ONES) & ~v & SWAR_HIGHS;
}

static inline uint64_t swar_hasbyte(uint64_t w, uint8_t c) {
    return swar_haszero(w ^ (SWAR_ONES * c));
}

static inline uint64_t swar_specials(uint64_t w, int quote) {
    uint64_t m = swar_hasbyte(w, '&') | swar_hasbyte(w, '<') | swar_hasbyte(w, '>');
    if (quote) {
        m |= swar_hasbyte(w, '"') | swar_hasbyte(w, '\'');
    }
    return m;
}

static inline Py_ssize_t escape_extra(Py_UCS4 ch, int quote) {
    switch (ch) {
    case '&':
        return 4; /* "&amp;"  */
    case '<':
    case '>':
        return 3; /* "&lt;"   */
    case '"':
        return quote ? 5 : 0; /* "&quot;" */
    case '\'':
        return quote ? 5 : 0; /* "&#x27;" */
    default:
        return 0;
    }
}

static inline Py_ssize_t write_escaped(int kind, void *data, Py_ssize_t o, Py_UCS4 ch, int quote) {
    const char *rep = NULL;
    int rlen = 0;
    switch (ch) {
    case '&':
        rep = "&amp;";
        rlen = 5;
        break;
    case '<':
        rep = "&lt;";
        rlen = 4;
        break;
    case '>':
        rep = "&gt;";
        rlen = 4;
        break;
    case '"':
        if (quote) {
            rep = "&quot;";
            rlen = 6;
        }
        break;
    case '\'':
        if (quote) {
            rep = "&#x27;";
            rlen = 6;
        }
        break;
    default:
        break;
    }
    if (rep != NULL) {
        for (int k = 0; k < rlen; k++) {
            PyUnicode_WRITE(kind, data, o + k, (Py_UCS4)rep[k]);
        }
        return rlen;
    }
    PyUnicode_WRITE(kind, data, o, ch);
    return 1;
}

PyObject *turbohtml_escape(PyObject *Py_UNUSED(module), PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"s", "quote", NULL};
    PyObject *s;
    int quote = 1;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "U|p:escape", kwlist, &s, &quote)) {
        return NULL;
    }

    int kind = PyUnicode_KIND(s);
    Py_ssize_t n = PyUnicode_GET_LENGTH(s);
    const void *data = PyUnicode_DATA(s);

    Py_ssize_t extra = 0;
    if (kind == PyUnicode_1BYTE_KIND) {
        const uint8_t *p = (const uint8_t *)data;
        Py_ssize_t i = 0;
        while (i + 8 <= n) {
            uint64_t w;
            memcpy(&w, p + i, 8);
            if (swar_specials(w, quote) == 0) {
                i += 8;
                continue;
            }
            for (int j = 0; j < 8; j++) {
                extra += escape_extra(p[i + j], quote);
            }
            i += 8;
        }
        for (; i < n; i++) {
            extra += escape_extra(p[i], quote);
        }
    } else {
        for (Py_ssize_t i = 0; i < n; i++) {
            extra += escape_extra(PyUnicode_READ(kind, data, i), quote);
        }
    }

    if (extra == 0) {
        /* Nothing to escape; return a true str (str subclasses are normalized). */
        return PyUnicode_FromObject(s);
    }

    Py_UCS4 maxchar = PyUnicode_MAX_CHAR_VALUE(s);
    PyObject *out = PyUnicode_New(n + extra, maxchar);
    if (out == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;   /* GCOVR_EXCL_LINE */
    }
    int okind = PyUnicode_KIND(out);
    void *odata = PyUnicode_DATA(out);
    Py_ssize_t o = 0;

    if (kind == PyUnicode_1BYTE_KIND) {
        /* a 1-byte input only gains ASCII escapes, so the output is 1-byte too */
        const uint8_t *p = (const uint8_t *)data;
        uint8_t *q = (uint8_t *)odata;
        Py_ssize_t i = 0;
        while (i + 8 <= n) {
            uint64_t w;
            memcpy(&w, p + i, 8);
            if (swar_specials(w, quote) == 0) {
                memcpy(q + o, p + i, 8);
                o += 8;
                i += 8;
                continue;
            }
            for (int j = 0; j < 8; j++) {
                o += write_escaped(okind, odata, o, p[i + j], quote);
            }
            i += 8;
        }
        for (; i < n; i++) {
            o += write_escaped(okind, odata, o, p[i], quote);
        }
    } else {
        for (Py_ssize_t i = 0; i < n; i++) {
            o += write_escaped(okind, odata, o, PyUnicode_READ(kind, data, i), quote);
        }
    }
    return out;
}
