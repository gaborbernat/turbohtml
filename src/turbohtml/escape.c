/* HTML escaping.

   Most strings contain nothing that needs escaping, so the 1-byte path scans a
   word (eight bytes) at a time with a SWAR has-zero test and skips all eight
   whenever none is special; that is why escape() can return the input untouched
   without inspecting most bytes one by one. UCS-2 / UCS-4 strings are rare here
   and use a plain scalar scan. */

#include "turbohtml.h"

#include <stdint.h>
#include <string.h>

#define SWAR_ONES 0x0101010101010101ULL
#define SWAR_HIGHS 0x8080808080808080ULL
#define SWAR_WORD 8

static inline uint64_t swar_haszero(uint64_t word) {
    return (word - SWAR_ONES) & ~word & SWAR_HIGHS;
}

static inline uint64_t swar_hasbyte(uint64_t word, uint8_t byte) {
    return swar_haszero(word ^ (SWAR_ONES * byte));
}

static inline uint64_t swar_specials(uint64_t word, int quote) {
    uint64_t mask = swar_hasbyte(word, '&') | swar_hasbyte(word, '<') | swar_hasbyte(word, '>');
    if (quote) {
        mask |= swar_hasbyte(word, '"') | swar_hasbyte(word, '\'');
    }
    return mask;
}

static inline Py_ssize_t escape_extra(Py_UCS4 character, int quote) {
    switch (character) {
    case '&':
        return 4; /* "&amp;" replaces one character with five */
    case '<':
    case '>':
        return 3; /* "&lt;" / "&gt;" */
    case '"':
        return quote ? 5 : 0; /* "&quot;" */
    case '\'':
        return quote ? 5 : 0; /* "&#x27;" */
    default:
        return 0;
    }
}

static inline Py_ssize_t write_escaped(int kind, void *data, Py_ssize_t offset, Py_UCS4 character, int quote) {
    const char *replacement = NULL;
    int replacement_len = 0;
    switch (character) {
    case '&':
        replacement = "&amp;";
        replacement_len = 5;
        break;
    case '<':
        replacement = "&lt;";
        replacement_len = 4;
        break;
    case '>':
        replacement = "&gt;";
        replacement_len = 4;
        break;
    case '"':
        if (quote) {
            replacement = "&quot;";
            replacement_len = 6;
        }
        break;
    case '\'':
        if (quote) {
            replacement = "&#x27;";
            replacement_len = 6;
        }
        break;
    default:
        break;
    }
    if (replacement != NULL) {
        for (int index = 0; index < replacement_len; index++) {
            PyUnicode_WRITE(kind, data, offset + index, (Py_UCS4)replacement[index]);
        }
        return replacement_len;
    }
    PyUnicode_WRITE(kind, data, offset, character);
    return 1;
}

PyObject *turbohtml_escape(PyObject *Py_UNUSED(module), PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"s", "quote", NULL};
    PyObject *text;
    int quote = 1;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "U|p:escape", kwlist, &text, &quote)) {
        return NULL;
    }

    int kind = PyUnicode_KIND(text);
    Py_ssize_t length = PyUnicode_GET_LENGTH(text);
    const void *data = PyUnicode_DATA(text);

    Py_ssize_t extra = 0;
    if (kind == PyUnicode_1BYTE_KIND) {
        const uint8_t *input = (const uint8_t *)data;
        Py_ssize_t pos = 0;
        while (pos + SWAR_WORD <= length) {
            uint64_t word;
            memcpy(&word, input + pos, SWAR_WORD);
            if (swar_specials(word, quote) == 0) {
                pos += SWAR_WORD;
                continue;
            }
            for (int lane = 0; lane < SWAR_WORD; lane++) {
                extra += escape_extra(input[pos + lane], quote);
            }
            pos += SWAR_WORD;
        }
        for (; pos < length; pos++) {
            extra += escape_extra(input[pos], quote);
        }
    } else {
        // wide strings are rare and the count scan below is scalar, so first use the
        // vectorized PyUnicode_FindChar to skip it entirely when nothing is special
        static const Py_UCS4 specials[] = {'&', '<', '>', '"', '\''};
        Py_ssize_t special_count = quote ? 5 : 3;
        int has_special = 0;
        for (Py_ssize_t index = 0; index < special_count; index++) {
            if (PyUnicode_FindChar(text, specials[index], 0, length, 1) >= 0) {
                has_special = 1;
                break;
            }
        }
        if (has_special) {
            for (Py_ssize_t pos = 0; pos < length; pos++) {
                extra += escape_extra(PyUnicode_READ(kind, data, pos), quote);
            }
        }
    }

    if (extra == 0) {
        /* normalize str subclasses to a real str even when nothing is escaped */
        return PyUnicode_FromObject(text);
    }

    Py_UCS4 maxchar = PyUnicode_MAX_CHAR_VALUE(text);
    PyObject *out = PyUnicode_New(length + extra, maxchar);
    if (out == NULL) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return NULL;   /* GCOVR_EXCL_LINE */
    }
    int out_kind = PyUnicode_KIND(out);
    void *out_data = PyUnicode_DATA(out);
    Py_ssize_t written = 0;

    if (kind == PyUnicode_1BYTE_KIND) {
        /* a 1-byte input gains only ASCII escapes, so the result stays 1-byte */
        const uint8_t *input = (const uint8_t *)data;
        uint8_t *output = (uint8_t *)out_data;
        Py_ssize_t pos = 0;
        while (pos + SWAR_WORD <= length) {
            uint64_t word;
            memcpy(&word, input + pos, SWAR_WORD);
            if (swar_specials(word, quote) == 0) {
                memcpy(output + written, input + pos, SWAR_WORD);
                written += SWAR_WORD;
                pos += SWAR_WORD;
                continue;
            }
            for (int lane = 0; lane < SWAR_WORD; lane++) {
                written += write_escaped(out_kind, out_data, written, input[pos + lane], quote);
            }
            pos += SWAR_WORD;
        }
        for (; pos < length; pos++) {
            written += write_escaped(out_kind, out_data, written, input[pos], quote);
        }
    } else {
        for (Py_ssize_t pos = 0; pos < length; pos++) {
            written += write_escaped(out_kind, out_data, written, PyUnicode_READ(kind, data, pos), quote);
        }
    }
    return out;
}
