/* Fuzz-only module functions, compiled only by meson's -Dfuzzing=true (see core/fuzzing.h).

   _fuzz_crash(kind) commits one memory error of the named kind. The fuzz driver runs each kind in a child process at
   startup and fails unless ASan reports it, so a run whose sanitizer is missing or blind cannot pass as clean, the
   check Fuzzilli runs before it fuzzes
   (https://github.com/googleprojectzero/fuzzilli/blob/281729bfc79f3bc9af398e4dce44933d6ea01dc4/Sources/Fuzzilli/Profiles/JSCProfile.swift#L92-L102).

   The PyMem allocator hook counts every PyMem_Malloc/Calloc/Realloc and fails the one at the injected position, the
   failure injection libxml2's fuzzers run
   (https://github.com/GNOME/libxml2/blob/c43dc98d27ac315a48d93dbd399c6c22cf7125b1/fuzz/fuzz.c#L83-L181). It wraps
   PYMEM_DOMAIN_MEM alone: the C core allocates through PyMem_*, while the object and raw domains also serve interpreter
   internals whose failures are not the C core's to handle. */

#include "core/common.h"
#include "dom/ownership.h"
#include "dom/tree_internal.h"

#include <stdlib.h>
#include <string.h>

/* Faulting loads go through a volatile pointer into this sink, so the optimizer keeps them. */
static volatile char th_fuzz_sink;

static void crash_heap_buffer_overflow(void) {
    char *block = malloc(16);
    th_fuzz_sink = ((const volatile char *)block)[16];
    free(block);
}

static void crash_heap_use_after_free(void) {
    char *block = malloc(16);
    free(block);
    th_fuzz_sink = ((const volatile char *)block)[0];
}

/* A one-byte allocation proves the arena unpoisons only the requested bytes; a 16-byte one, which fills its aligned
   slot exactly, proves the poisoned gap separates it from the next allocation. */
static void crash_arena_overflow(Py_ssize_t size) {
    th_tree *tree = th_tree_new();
    const volatile char *first = arena_alloc(tree, size);
    (void)arena_alloc(tree, size);
    th_fuzz_sink = first[size];
    th_tree_free(tree);
}

/* Wrap the parsed <html> element, drop the only reference so the wrapper parks on the freelist, then read it. */
static int crash_parked_wrapper(PyObject *module) {
    PyObject *document = PyObject_CallMethod(module, "parse", "s", "<p>");
    if (document == NULL) {
        return -1;
    }
    PyObject *wrapper = turbohtml_node_wrap_in(document, ((NodeObject *)document)->node->first_child);
    if (wrapper == NULL) {
        Py_DECREF(document);
        return -1;
    }
    Py_DECREF(wrapper);
    th_fuzz_sink = (char)(((const volatile NodeObject *)wrapper)->handle != NULL);
    Py_DECREF(document);
    return 0;
}

static PyObject *fuzz_crash(PyObject *module, PyObject *kind) {
    const char *name = PyUnicode_AsUTF8(kind);
    if (name == NULL) {
        return NULL;
    }
    if (strcmp(name, "heap-buffer-overflow") == 0) {
        crash_heap_buffer_overflow();
    } else if (strcmp(name, "heap-use-after-free") == 0) {
        crash_heap_use_after_free();
    } else if (strcmp(name, "arena-overflow") == 0) {
        crash_arena_overflow(1);
    } else if (strcmp(name, "arena-gap-overflow") == 0) {
        crash_arena_overflow(16);
    } else if (strcmp(name, "schema-arena-overflow") == 0) {
        th_fuzz_sink = th_fuzz_schema_arena_overread(1);
    } else if (strcmp(name, "schema-arena-gap-overflow") == 0) {
        th_fuzz_sink = th_fuzz_schema_arena_overread(16);
    } else if (strcmp(name, "parked-wrapper") == 0) {
        if (crash_parked_wrapper(module) < 0) {
            return NULL;
        }
    } else {
        PyErr_Format(PyExc_ValueError, "unknown crash kind %R", kind);
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMemAllocatorEx th_fuzz_inner;
static size_t th_fuzz_attempts;
static size_t th_fuzz_failure_pos;
static int th_fuzz_failed;

static int fuzz_should_fail(void) {
    if (++th_fuzz_attempts == th_fuzz_failure_pos) {
        th_fuzz_failed = 1;
        return 1;
    }
    return 0;
}

static void *fuzz_malloc(void *ctx, size_t size) {
    (void)ctx;
    return fuzz_should_fail() ? NULL : th_fuzz_inner.malloc(th_fuzz_inner.ctx, size);
}

static void *fuzz_calloc(void *ctx, size_t count, size_t size) {
    (void)ctx;
    return fuzz_should_fail() ? NULL : th_fuzz_inner.calloc(th_fuzz_inner.ctx, count, size);
}

static void *fuzz_realloc(void *ctx, void *ptr, size_t size) {
    (void)ctx;
    return fuzz_should_fail() ? NULL : th_fuzz_inner.realloc(th_fuzz_inner.ctx, ptr, size);
}

static void fuzz_free(void *ctx, void *ptr) {
    (void)ctx;
    th_fuzz_inner.free(th_fuzz_inner.ctx, ptr);
}

/* Close the current injection window and open one that fails the position-th PyMem allocation, or only counts for
   position 0. Returns the closed window as (allocations, failed): one call does both, so the harness allocates nothing
   between reading a window and opening the next. */
static PyObject *fuzz_inject_failure(PyObject *module, PyObject *position) {
    (void)module;
    Py_ssize_t value = PyLong_AsSsize_t(position);
    if (value == -1 && PyErr_Occurred()) {
        return NULL;
    }
    if (value < 0) {
        PyErr_SetString(PyExc_ValueError, "the failure position must not be negative");
        return NULL;
    }
    size_t attempts = th_fuzz_attempts;
    int failed = th_fuzz_failed;
    th_fuzz_attempts = 0;
    th_fuzz_failure_pos = (size_t)value;
    th_fuzz_failed = 0;
    return Py_BuildValue("(nO)", (Py_ssize_t)attempts, failed ? Py_True : Py_False);
}

static PyMethodDef fuzz_methods[] = {
    {"_fuzz_crash", fuzz_crash, METH_O, NULL},
    {"_fuzz_inject_failure", fuzz_inject_failure, METH_O, NULL},
    {NULL, NULL, 0, NULL},
};

int th_fuzz_register(PyObject *module) {
    /* A second import, in a subinterpreter, would wrap the hook in itself and count every allocation twice. */
    static int installed;
    if (!installed) {
        PyMemAllocatorEx hook = {NULL, fuzz_malloc, fuzz_calloc, fuzz_realloc, fuzz_free};
        PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &th_fuzz_inner);
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &hook);
        installed = 1;
    }
    return PyModule_AddFunctions(module, fuzz_methods);
}
