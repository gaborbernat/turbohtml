/* turbohtml._html - module definition wiring the per-feature implementations.

   escape() is implemented in escape.c and unescape() in unescape.c; this file
   only declares the module and its methods. The module holds no mutable state
   (immutable str inputs, read-only tables), so it declares free-threading and
   per-interpreter GIL support where the running interpreter is new enough.
   Only public, version-portable APIs are used, so the same sources build on
   CPython 3.10 through 3.15. */

#include "turbohtml.h"

PyDoc_STRVAR(escape_doc, "escape(s, quote=True)\n--\n\n"
                         "Replace special characters \"&\", \"<\" and \">\" with HTML-safe sequences.\n\n"
                         "If the optional flag quote is true (the default), the quotation mark\n"
                         "characters, both double quote (\") and single quote ('), are also translated.");

PyDoc_STRVAR(unescape_doc, "unescape(s, /)\n--\n\n"
                           "Convert all named and numeric character references in s to the\n"
                           "corresponding Unicode characters, following the HTML5 rules.");

static PyMethodDef html_methods[] = {
    {"escape", (PyCFunction)(void (*)(void))turbohtml_escape, METH_VARARGS | METH_KEYWORDS, escape_doc},
    {"unescape", turbohtml_unescape, METH_O, unescape_doc},
    {NULL, NULL, 0, NULL},
};

static PyModuleDef_Slot html_slots[] = {
#if PY_VERSION_HEX >= 0x030C0000
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
#endif
#if PY_VERSION_HEX >= 0x030D0000
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    {0, NULL},
};

static struct PyModuleDef htmlmodule = {
    PyModuleDef_HEAD_INIT, .m_name = "_html",         .m_doc = "C accelerator for turbohtml escaping and unescaping.",
    .m_size = 0,           .m_methods = html_methods, .m_slots = html_slots,
};

PyMODINIT_FUNC PyInit__html(void) {
    return PyModuleDef_Init(&htmlmodule);
}
