#define _GNU_SOURCE
#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef int (*InputCallback)(const uint8_t *, size_t);
typedef size_t (*CustomMutator)(uint8_t *, size_t, size_t, unsigned int);

int turbohtml_real_fuzzer_driver(int *, char ***, InputCallback);
size_t LLVMFuzzerMutate(uint8_t *, size_t, size_t);
static int run_input(const uint8_t *, size_t);

static InputCallback input_callback;
static _Thread_local int rejected;

#ifdef ATHERIS_BRIDGE_COVERAGE
void __gcov_dump(void);

/* Atheris terminates before gcov shutdown. */
void turbohtml_fuzz_dump_coverage(void) {
    __gcov_dump();
} /* GCOVR_EXCL_LINE -- the profiler snapshot precedes its own return. */
#endif

void turbohtml_fuzz_reject_input(void) {
    rejected = 1;
}

int LLVMFuzzerRunDriver(int *argc, char ***argv, InputCallback callback) {
    fputs("ATHERIS_REJECTION_BRIDGE=1\n", stderr);
    input_callback = callback;
    return turbohtml_real_fuzzer_driver(argc, argv, run_input);
}

size_t LLVMFuzzerCustomMutator(uint8_t *data, size_t size, size_t max_size, unsigned int seed) {
    static CustomMutator mutator;
    if (!mutator) {
        mutator = (CustomMutator)dlsym(RTLD_NEXT, "LLVMFuzzerCustomMutator");
        if (mutator) {
            fputs("ATHERIS_CUSTOM_MUTATOR_BRIDGE=1\n", stderr);
        }
    }
    return mutator ? mutator(data, size, max_size, seed) : LLVMFuzzerMutate(data, size, max_size);
}

static int run_input(const uint8_t *data, size_t size) {
    rejected = 0;
    int result = input_callback(data, size);
    return rejected ? -1 : result;
}
