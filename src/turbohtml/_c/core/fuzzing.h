/* The fuzz-only build mode, set by meson's -Dfuzzing=true. Chromium and libxml2 compile checks that must never ship
   under FUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION
   (https://github.com/GNOME/libxml2/blob/c43dc98d27ac315a48d93dbd399c6c22cf7125b1/xpath.c#L111-L118). A production
   build includes this header too, so outside that macro it may only define macros: any declaration or definition here
   would change the preprocessed production output that tools/preprocess_identity.py keeps byte-identical. The header
   needs no CPython, so the standalone harnesses can include it. */

#ifndef TURBOHTML_CORE_FUZZING_H
#define TURBOHTML_CORE_FUZZING_H

#ifdef FUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION

/* The detection asan_interface.h uses for its own region macros: clang answers __has_feature, gcc defines
   __SANITIZE_ADDRESS__. Without ASan the macros compile to nothing, which the crash self-test then reports. */
#ifdef __has_feature
#if __has_feature(address_sanitizer)
#define TH_FUZZ_ASAN 1
#endif
#elif defined(__SANITIZE_ADDRESS__)
#define TH_FUZZ_ASAN 1
#endif

#ifdef TH_FUZZ_ASAN
#include <sanitizer/asan_interface.h>
#define TH_FUZZ_POISON(addr, size) ASAN_POISON_MEMORY_REGION((addr), (size))
#define TH_FUZZ_UNPOISON(addr, size) ASAN_UNPOISON_MEMORY_REGION((addr), (size))
#else
#define TH_FUZZ_POISON(addr, size) ((void)(addr), (void)(size))
#define TH_FUZZ_UNPOISON(addr, size) ((void)(addr), (void)(size))
#endif

/* Growable arrays start at one slot, so the second append takes the realloc path. libxml2's fuzz build starts its
   XPath step and value stacks at 1 for the same reason
   (https://github.com/GNOME/libxml2/blob/c43dc98d27ac315a48d93dbd399c6c22cf7125b1/xpath.c#L947-L951). */
#define TH_INITIAL_CAPACITY(production) ((void)(production), 1)

/* Recursion and nesting caps drop to a tenth, so the limit paths fire on short inputs. libxml2's fuzz build lowers
   XPATH_MAX_RECURSION_DEPTH from 5000 to 500 the same way. The tree depth cap keeps its value: it shapes parse output
   and matches the browsers. */
#define TH_DEPTH_LIMIT(production) ((production) / 10)

/* Arena allocations reserve this gap after the requested bytes and keep it poisoned. ASan tracks addressability in
   8-byte granules, so a request that ends on a granule boundary would otherwise sit flush against its neighbor and an
   over-read would land in live memory. 16 keeps every allocation on the arena's 16-byte alignment. */
#define TH_FUZZ_ARENA_GAP 16

#else

#define TH_INITIAL_CAPACITY(production) production
#define TH_DEPTH_LIMIT(production) production

#endif

#endif /* TURBOHTML_CORE_FUZZING_H */
