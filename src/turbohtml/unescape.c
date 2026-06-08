/* HTML unescaping.

   unescape() makes a single pass over the input, resolving numeric and named
   character references following the HTML5 rules. Named references are found by
   binary search over the generated table, with longest-prefix matching for
   references that omit the trailing semicolon; numeric references apply the
   spec's correction tables. Output is built into a Py_UCS4 buffer (unescape
   never lengthens the text) and then materialised at the right width. */

#include "turbohtml.h"

#include <stdint.h>
#include <string.h>

#include "html_entities.h"

static int cmp_name(const char *a, Py_ssize_t alen, const char *b, unsigned blen) {
    Py_ssize_t m = alen < (Py_ssize_t)blen ? alen : (Py_ssize_t)blen;
    int c = memcmp(a, b, (size_t)m);
    if (c != 0) {
        return c < 0 ? -1 : 1;
    }
    if (alen == (Py_ssize_t)blen) {
        return 0;
    }
    return alen < (Py_ssize_t)blen ? -1 : 1;
}

static const html5_entity *find_entity(const char *name, Py_ssize_t len) {
    int lo = 0, hi = html5_count - 1;
    while (lo <= hi) {
        int mid = (lo + hi) >> 1;
        const html5_entity *e = &html5_entities[mid];
        int c = cmp_name(name, len, e->name, e->name_len);
        if (c == 0) {
            return e;
        }
        if (c < 0) {
            hi = mid - 1;
        } else {
            lo = mid + 1;
        }
    }
    return NULL;
}

static int find_invalid_charref(Py_UCS4 num, Py_UCS4 *cp) {
    int lo = 0, hi = invalid_charref_count - 1;
    while (lo <= hi) {
        int mid = (lo + hi) >> 1;
        Py_UCS4 v = invalid_charrefs[mid].num;
        if (v == num) {
            *cp = invalid_charrefs[mid].cp;
            return 1;
        }
        if (num < v) {
            hi = mid - 1;
        } else {
            lo = mid + 1;
        }
    }
    return 0;
}

static int is_invalid_codepoint(Py_UCS4 num) {
    int lo = 0, hi = invalid_codepoint_count - 1;
    while (lo <= hi) {
        int mid = (lo + hi) >> 1;
        Py_UCS4 v = invalid_codepoints[mid];
        if (v == num) {
            return 1;
        }
        if (num < v) {
            hi = mid - 1;
        } else {
            lo = mid + 1;
        }
    }
    return 0;
}

static inline int is_name_char(Py_UCS4 c) {
    /* [^\t\n\f <&#;] from the reference HTML5 charref regex. */
    switch (c) {
    case '\t':
    case '\n':
    case '\x0c':
    case ' ':
    case '<':
    case '&':
    case '#':
    case ';':
        return 0;
    default:
        return 1;
    }
}

static inline int hex_value(Py_UCS4 c) {
    if (c >= '0' && c <= '9')
        return (int)(c - '0');
    if (c >= 'a' && c <= 'f')
        return (int)(c - 'a') + 10;
    if (c >= 'A' && c <= 'F')
        return (int)(c - 'A') + 10;
    return -1;
}

static inline void emit(Py_UCS4 *out, Py_ssize_t *o, Py_UCS4 *maxchar, Py_UCS4 c) {
    out[*o] = c;
    if (c > *maxchar) {
        *maxchar = c;
    }
    (*o)++;
}

/* Parse a character reference starting with '&' at index i.  On a match, append
   the replacement to out and return the number of input characters consumed
   (including '&').  Return 0 when no reference matches. */
static Py_ssize_t parse_charref(int kind, const void *data, Py_ssize_t n, Py_ssize_t i, Py_UCS4 *out, Py_ssize_t *o,
                                Py_UCS4 *maxchar) {
    Py_ssize_t p = i + 1;
    if (p >= n) {
        return 0;
    }
    Py_UCS4 c = PyUnicode_READ(kind, data, p);

    if (c == '#') {
        Py_ssize_t d = p + 1;
        int hex = 0;
        if (d < n) {
            Py_UCS4 x = PyUnicode_READ(kind, data, d);
            if (x == 'x' || x == 'X') {
                hex = 1;
                d++;
            }
        }
        Py_UCS4 num = 0;
        int overflow = 0;
        Py_ssize_t start = d;
        while (d < n) {
            Py_UCS4 x = PyUnicode_READ(kind, data, d);
            if (hex) {
                int v = hex_value(x);
                if (v < 0) {
                    break;
                }
                num = num * 16 + (Py_UCS4)v;
            } else {
                if (x < '0' || x > '9') {
                    break;
                }
                num = num * 10 + (x - '0');
            }
            if (num > 0x110000) {
                num = 0x110000; /* cap to trigger the > 0x10FFFF branch below */
                overflow = 1;
            }
            d++;
        }
        if (d == start) {
            return 0; /* no digits: not a reference */
        }
        if (d < n && PyUnicode_READ(kind, data, d) == ';') {
            d++; /* optional trailing ';' */
        }

        Py_UCS4 repl;
        if (!overflow && find_invalid_charref(num, &repl)) {
            emit(out, o, maxchar, repl);
        } else if ((num >= 0xD800 && num <= 0xDFFF) || num > 0x10FFFF) {
            emit(out, o, maxchar, 0xFFFD);
        } else if (is_invalid_codepoint(num)) {
            /* maps to the empty string */
        } else {
            emit(out, o, maxchar, num);
        }
        return d - i;
    }

    if (!is_name_char(c)) {
        return 0; /* e.g. "&;", "& ", "&&" */
    }

    Py_UCS4 ucs[HTML5_MAX_NAME_LEN];
    char ascii[HTML5_MAX_NAME_LEN + 1];
    int nlen = 0;
    Py_ssize_t d = p;
    while (d < n && nlen < HTML5_MAX_NAME_LEN) {
        Py_UCS4 x = PyUnicode_READ(kind, data, d);
        if (!is_name_char(x)) {
            break;
        }
        ucs[nlen] = x;
        ascii[nlen] = (x < 128) ? (char)x : (char)0x01; /* 0x01 never matches */
        nlen++;
        d++;
    }
    int semi = 0;
    if (d < n && PyUnicode_READ(kind, data, d) == ';') {
        ascii[nlen] = ';';
        semi = 1;
        d++;
    }
    int toklen = nlen + semi;

    const html5_entity *e = find_entity(ascii, toklen);
    int matchlen = toklen;
    if (e == NULL) {
        for (int x = toklen - 1; x >= 2; x--) {
            e = find_entity(ascii, x);
            if (e != NULL) {
                matchlen = x;
                break;
            }
        }
    }

    if (e == NULL) {
        emit(out, o, maxchar, '&');
        for (int k = 0; k < nlen; k++) {
            emit(out, o, maxchar, ucs[k]);
        }
        if (semi) {
            emit(out, o, maxchar, ';');
        }
        return d - i;
    }

    emit(out, o, maxchar, e->cp0);
    if (e->cp1) {
        emit(out, o, maxchar, e->cp1);
    }
    for (int k = matchlen; k < toklen; k++) {
        emit(out, o, maxchar, (k < nlen) ? ucs[k] : (Py_UCS4)';');
    }
    return d - i;
}

PyObject *turbohtml_unescape(PyObject *Py_UNUSED(module), PyObject *arg) {
    if (!PyUnicode_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "unescape() argument must be str");
        return NULL;
    }
    Py_ssize_t n = PyUnicode_GET_LENGTH(arg);
    int kind = PyUnicode_KIND(arg);
    const void *data = PyUnicode_DATA(arg);

    if (PyUnicode_FindChar(arg, '&', 0, n, 1) < 0) {
        return Py_NewRef(arg); /* no reference; preserve the input object */
    }

    /* We only get here after finding '&', so n >= 1; unescape never lengthens
       the text, so n code points is a safe upper bound for the output. */
    Py_UCS4 *out = PyMem_New(Py_UCS4, n); /* GCOVR_EXCL_BR_LINE: size-overflow guard unreachable for valid lengths */
    if (out == NULL) {                    /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return PyErr_NoMemory();          /* GCOVR_EXCL_LINE */
    }
    Py_ssize_t o = 0;
    Py_UCS4 maxchar = 0;
    Py_ssize_t i = 0;
    while (i < n) {
        Py_UCS4 ch = PyUnicode_READ(kind, data, i);
        if (ch != '&') {
            emit(out, &o, &maxchar, ch);
            i++;
            continue;
        }
        Py_ssize_t consumed = parse_charref(kind, data, n, i, out, &o, &maxchar);
        if (consumed == 0) {
            emit(out, &o, &maxchar, '&');
            i++;
        } else {
            i += consumed;
        }
    }

    PyObject *res = PyUnicode_New(o, maxchar);
    if (res == NULL) {   /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        PyMem_Free(out); /* GCOVR_EXCL_LINE */
        return NULL;     /* GCOVR_EXCL_LINE */
    }
    int rkind = PyUnicode_KIND(res);
    void *rdata = PyUnicode_DATA(res);
    for (Py_ssize_t k = 0; k < o; k++) {
        PyUnicode_WRITE(rkind, rdata, k, out[k]);
    }
    PyMem_Free(out);
    return res;
}
