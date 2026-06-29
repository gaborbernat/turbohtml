/* The public entry point: parse a script and print it minified. A parse error is
   reported to the caller (errbuf) rather than swallowed, so an unminifiable or
   malformed script fails loudly instead of passing through unchanged. The HTML
   inline-<script> path adds its own fallback so a single bad script cannot break
   document serialization; the standalone minify_js() surfaces the error. */

#include "serialize/js/internal.h"
#include "serialize/js/minify.h"

Py_UCS4 *th_js_minify(const Py_UCS4 *src, Py_ssize_t len, int fold, int mangle, Py_ssize_t *out_len, char *errbuf,
                      size_t errlen) {
    jm_program *prog = jm_parse(src, len, errbuf, errlen);
    if (prog == NULL) {
        return NULL; /* errbuf carries the message; empty on allocation failure */
    }
    if (fold) {
        jm_fold(prog);
    }
    if (mangle) {
        jm_mangle(prog);
    }
    if (fold && mangle) {
        jm_fold(prog); /* fold a literal the const-inliner just exposed (`const x=42;x*2` -> `42*2`) */
    }
    Py_UCS4 *out = jm_print(prog, out_len);
    jm_program_free(prog);
    if (out == NULL && errlen > 0) { /* GCOVR_EXCL_BR_LINE: allocation-failure path */
        errbuf[0] = '\0';            /* GCOVR_EXCL_LINE */
    } /* GCOVR_EXCL_LINE */
    return out;
}
