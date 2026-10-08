#define _GNU_SOURCE
#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

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

/* Inputs start with the [opts][failure_pos][max_chunk] header of atheris_header.py. A mutation over the whole input
   would shift or resize those fields, so each call mutates one field, picked with probability 1/10 each, or else the
   payload, as libxml2's xmlFuzzMutateChunks does with xml.c's field table
   (https://github.com/GNOME/libxml2/blob/c43dc98d27ac315a48d93dbd399c6c22cf7125b1/fuzz/fuzz.c#L551-L601,
   https://github.com/GNOME/libxml2/blob/c43dc98d27ac315a48d93dbd399c6c22cf7125b1/fuzz/xml.c#L250-L262). */
enum { HEADER_FIELDS = 3, FIELD_SIZE = 4, PROBABILITY_ONE = 1 << 16, FIELD_PROBABILITY = PROBABILITY_ONE / 10 };

size_t LLVMFuzzerCustomMutator(uint8_t *data, size_t size, size_t max_size, unsigned int seed) {
    static CustomMutator payload_mutator;
    if (!payload_mutator) {
        payload_mutator = (CustomMutator)dlsym(RTLD_NEXT, "LLVMFuzzerCustomMutator");
        if (payload_mutator) {
            fputs("ATHERIS_CUSTOM_MUTATOR_BRIDGE=1\n", stderr);
        }
    }
    unsigned int chance = seed % PROBABILITY_ONE;
    size_t offset = 0;
    size_t field_size = 0;
    for (int field = 0; field < HEADER_FIELDS; field++) {
        if (offset + FIELD_SIZE > size || offset + FIELD_SIZE >= max_size || chance < FIELD_PROBABILITY) {
            field_size = FIELD_SIZE;
            break;
        }
        offset += FIELD_SIZE;
        chance -= FIELD_PROBABILITY;
    }
    size_t region = size - offset;
    size_t max_region = max_size - offset;
    if (field_size) {
        region = region < field_size ? region : field_size;
        max_region = max_region < field_size ? max_region : field_size;
    }
    size_t mutated = !field_size && payload_mutator ? payload_mutator(data + offset, region, max_region, seed)
                                                    : LLVMFuzzerMutate(data + offset, region, max_region);
    if (size <= offset + region) {
        return offset + mutated;
    }
    /* A header field that shrank keeps its width, zero-filled, so the fields after it stay aligned. */
    memset(data + offset + mutated, 0, region - mutated);
    return size;
}

static int run_input(const uint8_t *data, size_t size) {
    rejected = 0;
    int result = input_callback(data, size);
    return rejected ? -1 : result;
}
