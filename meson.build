project(
    'turbohtml',
    'c',
    version: run_command(['tools/generate_version.py'], check: true).stdout().strip(),
    meson_version: '>=1.5.0',
    default_options: ['c_std=c11', 'warning_level=2'],
)

# Freeze the git-derived version into the sdist so wheels built from it need no git history.
meson.add_dist_script('tools/generate_version.py', '--write', 'src/turbohtml/_version.py', '--meson-dist')

# Keep the development-only submodule corpora out of the sdist regardless of local checkout state.
meson.add_dist_script('tools/prune_dist.py')

py = import('python').find_installation(pure: false)

py.extension_module(
    '_html',
    [
        'src/turbohtml/_c/core/module.c',
        'src/turbohtml/_c/tokenizer/charref.c',
        'src/turbohtml/_c/tokenizer/statemachine.c',
        'src/turbohtml/_c/tokenizer/token.c',
        'src/turbohtml/_c/tokenizer/tokenizer.c',
        'src/turbohtml/_c/dom/tree.c',
        'src/turbohtml/_c/dom/binding.c',
        'src/turbohtml/_c/dom/nodes.c',
        'src/turbohtml/_c/serialize/escape.c',
        'src/turbohtml/_c/serialize/unescape.c',
        'src/turbohtml/_c/serialize/markup.c',
        'src/turbohtml/_c/query/xpath/xpath.c',
        'src/turbohtml/_c/features/sanitize.c',
        'src/turbohtml/_c/features/linkify.c',
        'src/turbohtml/_c/features/links.c',
        'src/turbohtml/_c/features/annotation.c',
    ],
    include_directories: include_directories('src/turbohtml/_c'),
    install: true,
    subdir: 'turbohtml',
)

py.install_sources(
    [
        'src/turbohtml/__init__.py',
        'src/turbohtml/_html.pyi',
        'src/turbohtml/_links.py',
        'src/turbohtml/_xpath.py',
        'src/turbohtml/bleach_compat.py',
        'src/turbohtml/html_parser.py',
        'src/turbohtml/linkify.py',
        'src/turbohtml/markup.py',
        'src/turbohtml/query.py',
        'src/turbohtml/sanitizer.py',
        'src/turbohtml/py.typed',
    ],
    subdir: 'turbohtml',
)
