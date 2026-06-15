/* turbohtml._html - module definition wiring the per-feature implementations.

   escape()/unescape() are stateless string functions (escape.c, unescape.c).
   The tokenizer adds the Token and Tokenizer types plus tokenize(); those heap
   types live in per-module state so the module supports sub-interpreters and
   the free-threaded build. These sources use only public, version-portable
   APIs, so they build on CPython 3.10 through 3.15. */

#include "turbohtml.h"

#include "tokenizer_py.h"

PyDoc_STRVAR(escape_doc, "escape(s, quote=True)\n--\n\n"
                         "Replace special characters \"&\", \"<\" and \">\" with HTML-safe sequences.\n\n"
                         "If the optional flag quote is true (the default), the quotation mark\n"
                         "characters, both double quote (\") and single quote ('), are also translated.");

PyDoc_STRVAR(unescape_doc, "unescape(s, /)\n--\n\n"
                           "Convert all named and numeric character references in s to the\n"
                           "corresponding Unicode characters, following the HTML5 rules.");

PyDoc_STRVAR(tokenize_doc, "tokenize(s, /)\n--\n\n"
                           "Tokenize a whole HTML string, returning an iterator of Token objects\n"
                           "following the WHATWG tokenization algorithm.");

PyDoc_STRVAR(parse_doc, "parse(html, /)\n--\n\n"
                        "Parse a whole HTML document with the WHATWG tree-construction algorithm\n"
                        "and return a navigable Document.");

PyDoc_STRVAR(parse_fragment_doc, "parse_fragment(html, context='div')\n--\n\n"
                                 "Parse an HTML fragment as the innerHTML of a context element and return\n"
                                 "that context Element with the parsed nodes as its children. context is a\n"
                                 "tag name, optionally namespaced (e.g. 'td', 'svg path').");

static PyMethodDef html_methods[] = {
    {"escape", (PyCFunction)(void (*)(void))turbohtml_escape, METH_VARARGS | METH_KEYWORDS, escape_doc},
    {"unescape", turbohtml_unescape, METH_O, unescape_doc},
    {"tokenize", turbohtml_tokenize, METH_O, tokenize_doc},
    {"parse", turbohtml_parse, METH_O, parse_doc},
    {"parse_fragment", (PyCFunction)(void (*)(void))turbohtml_tree_parse_fragment, METH_VARARGS | METH_KEYWORDS,
     parse_fragment_doc},
    {"_tokenize_states", turbohtml_tokenize_states, METH_VARARGS, NULL},
    {"_parse_tree", turbohtml_parse_tree, METH_O, NULL},
    {"_parse_fragment", turbohtml_parse_fragment, METH_VARARGS, NULL},
    {"_parse_only", turbohtml_parse_only, METH_O, NULL},
    {NULL, NULL, 0, NULL},
};

static int html_exec(PyObject *module) {
    module_state *state = PyModule_GetState(module);
    if (token_register(module, state) < 0) { /* GCOVR_EXCL_BR_LINE: allocation failure cannot be forced from a test */
        return -1;                           /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    /* allocation failure cannot be forced from a test */
    if (tokenizer_register(module, state) < 0) { /* GCOVR_EXCL_BR_LINE */
        return -1;                               /* GCOVR_EXCL_LINE: allocation-failure path */
    }
    return tree_register(module, state);
}

static int html_traverse(PyObject *module, visitproc visit, void *arg) {
    module_state *state = PyModule_GetState(module);
    Py_VISIT(state->token_type); /* GCOVR_EXCL_BR_LINE: Py_VISIT's NULL arm is dead, module state is populated for the
                                    module's lifetime */
    Py_VISIT(state->tokenizer_type); /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->iter_type);      /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->kind_enum);      /* GCOVR_EXCL_BR_LINE: same */
    for (int index = 0; index < 5; index++) {
        Py_VISIT(state->kinds[index]); /* GCOVR_EXCL_BR_LINE: same */
    }
    Py_VISIT(state->node_type);          /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->element_type);       /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->text_type);          /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->comment_type);       /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->doctype_type);       /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->document_type);      /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->handle_type);        /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->walker_type);        /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->string_walker_type); /* GCOVR_EXCL_BR_LINE: same */
    Py_VISIT(state->namespace_enum);     /* GCOVR_EXCL_BR_LINE: same */
    for (int index = 0; index < 3; index++) {
        Py_VISIT(state->namespaces[index]); /* GCOVR_EXCL_BR_LINE: same */
    }
    return 0;
}

static int html_clear(PyObject *module) {
    module_state *state = PyModule_GetState(module);
    Py_CLEAR(state->token_type);
    Py_CLEAR(state->tokenizer_type);
    Py_CLEAR(state->iter_type);
    Py_CLEAR(state->kind_enum);
    for (int index = 0; index < 5; index++) {
        Py_CLEAR(state->kinds[index]);
    }
    Py_CLEAR(state->node_type);
    Py_CLEAR(state->element_type);
    Py_CLEAR(state->text_type);
    Py_CLEAR(state->comment_type);
    Py_CLEAR(state->doctype_type);
    Py_CLEAR(state->document_type);
    Py_CLEAR(state->handle_type);
    Py_CLEAR(state->walker_type);
    Py_CLEAR(state->string_walker_type);
    Py_CLEAR(state->namespace_enum);
    for (int index = 0; index < 3; index++) {
        Py_CLEAR(state->namespaces[index]);
    }
    return 0;
}

static void html_free(void *module) {
    (void)html_clear((PyObject *)module);
}

static PyModuleDef_Slot html_slots[] = {
    {Py_mod_exec, html_exec},
#if PY_VERSION_HEX >= 0x030C0000
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
#endif
#if PY_VERSION_HEX >= 0x030D0000
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    {0, NULL},
};

static struct PyModuleDef htmlmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_html",
    .m_doc = "C accelerator for turbohtml escaping, unescaping, and tokenizing.",
    .m_size = sizeof(module_state),
    .m_methods = html_methods,
    .m_slots = html_slots,
    .m_traverse = html_traverse,
    .m_clear = html_clear,
    .m_free = html_free,
};

// NOLINTNEXTLINE(misc-use-internal-linkage): the module init must be exported under this exact name
PyMODINIT_FUNC PyInit__html(void) {
    return PyModuleDef_Init(&htmlmodule);
}
