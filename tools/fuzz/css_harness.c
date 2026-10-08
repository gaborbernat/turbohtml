/* Standalone sanitizer harness for the CSS minifier core (src/turbohtml/_c/css/minify/css.c).

   Compiled with CSS_MINIFY_STANDALONE the tokenizer, grammar and value engine allocate through libc and include no
   CPython header, so this driver runs them under AddressSanitizer, UndefinedBehaviorSanitizer or MemorySanitizer with
   no interpreter, the same decoupling tools/js_minify_harness.c uses for the JavaScript engine. Each input is minified
   as a stylesheet and as a style="" declaration list, at baseline 0 and at a recent Baseline year, and each output is
   minified again so the fixpoint path allocates too. Every returned buffer is freed, so a miss is a real leak.

   Build (macOS, ASan+UBSan; LSan is unavailable on Apple clang):
     clang -DCSS_MINIFY_STANDALONE -fsanitize=address,undefined -g -O1 -fno-omit-frame-pointer \
       -I src/turbohtml/_c tools/fuzz/css_harness.c src/turbohtml/_c/css/minify/css.c -lm -o /tmp/cssmin
   Coverage-guided (libFuzzer): add -DCSS_MINIFY_FUZZ -fsanitize=fuzzer.

   Usage: cssmin [file ...]  -- runs the built-in edge cases, then each file's bytes. */

#ifndef CSS_MINIFY_STANDALONE
#define CSS_MINIFY_STANDALONE
#endif

#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef ptrdiff_t Py_ssize_t;

#include "css/minify/css.h"

/* CSSMinify's baseline is a Baseline year (https://web.dev/baseline); 0 targets every browser */
static const int BASELINES[] = {0, 2025};

static void run_bytes(const unsigned char *bytes, size_t len) {
    for (int inline_mode = 0; inline_mode <= 1; inline_mode++) {
        for (size_t index = 0; index < sizeof(BASELINES) / sizeof(BASELINES[0]); index++) {
            Py_ssize_t out_len = 0;
            unsigned char *out = th_minify_css_bytes(bytes, (Py_ssize_t)len, inline_mode, BASELINES[index], &out_len);
            if (out != NULL) {
                Py_ssize_t again_len = 0;
                free(th_minify_css_bytes(out, out_len, inline_mode, BASELINES[index], &again_len));
                free(out);
            }
        }
    }
}

static void run_file(const char *path, long *files) {
    FILE *handle = fopen(path, "rb");
    if (handle == NULL) {
        fprintf(stderr, "skip %s: %s\n", path, strerror(errno));
        return;
    }
    fseek(handle, 0, SEEK_END);
    long size = ftell(handle);
    fseek(handle, 0, SEEK_SET);
    unsigned char *buffer = malloc((size_t)size); /* sized to the input, so ASan flags a read past its end */
    if (buffer == NULL) {
        perror("malloc");
        exit(2);
    }
    size_t read = fread(buffer, 1, (size_t)size, handle);
    fclose(handle);
    *files += 1;
    run_bytes(buffer, read);
    free(buffer);
}

/* Inputs that reach the escape respelling, nesting, at-rule, number and color paths without an external corpus. */
static void run_builtins(long *cases) {
    static const char *const snippets[] = {
        "",
        " ",
        ";",
        "a{}",
        "a{color:red}",
        "color:#ff0000;margin:0px 0px 0px 0px",
        "@media (min-width:100px){a{b:c}}",
        "a{&:hover{color:blue}}",
        "@charset \"utf-8\";a{b:c}",
        "\\61 {c\\6f lor:red}",
        "#\\31 23{x:1}",
        "a{width:calc(100% - (2*3px))}",
        "a{transform:rotate(0.50turn) scale(1.0)}",
        "a{font:italic bold 12px/30px Georgia,serif}",
        "a{background:url( \"x y.png\" )}",
        "a{x:1e3;y:.0;z:-0.0}",
        "</style><a{}",
        "a{b:c",
        "/* unterminated",
        "a::before{content:\"\\\"\"}",
        "\xef\xbb\xbf a{b:c}",
    };
    for (size_t index = 0; index < sizeof(snippets) / sizeof(snippets[0]); index++) {
        run_bytes((const unsigned char *)snippets[index], strlen(snippets[index]));
        *cases += 1;
    }
}

#ifdef CSS_MINIFY_FUZZ
int LLVMFuzzerTestOneInput(const unsigned char *data, size_t size) {
    run_bytes(data, size);
    return 0;
}
#else
int main(int argc, char **argv) {
    long cases = 0;
    long files = 0;
    run_builtins(&cases);
    for (int index = 1; index < argc; index++) {
        run_file(argv[index], &files);
    }
    printf("css harness: %ld builtins + %ld files, no sanitizer abort\n", cases, files);
    return 0;
}
#endif
