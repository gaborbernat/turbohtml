project(
    'turbohtml',
    'c',
    version: '0.1.0',
    meson_version: '>=1.5.0',
    default_options: ['c_std=c11', 'warning_level=2'],
)

py = import('python').find_installation(pure: false)

py.extension_module(
    '_html',
    [
        'src/turbohtml/_htmlmodule.c',
        'src/turbohtml/escape.c',
        'src/turbohtml/unescape.c',
    ],
    include_directories: include_directories('src/turbohtml'),
    install: true,
    subdir: 'turbohtml',
)

py.install_sources(
    [
        'src/turbohtml/__init__.py',
        'src/turbohtml/_html.pyi',
        'src/turbohtml/py.typed',
    ],
    subdir: 'turbohtml',
)
