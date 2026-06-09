# turbohtml

A fast, fully typed HTML toolkit for Python, powered by a C-accelerated core. `turbohtml` provides spec-correct HTML
escaping and unescaping that match the standard library byte for byte while running several times faster, and it is
ready for the free-threaded build.

## Install

```console
$ pip install turbohtml
```

Wheels are published per interpreter for CPython 3.10–3.15 (including free-threading), so there is nothing to compile.

## Usage

Escape text before interpolating it into HTML so it cannot break out of its context:

```pycon
>>> import turbohtml
>>> turbohtml.escape('<a href="?x=1&y=2">Tom & Jerry</a>')
'&lt;a href=&quot;?x=1&amp;y=2&quot;&gt;Tom &amp; Jerry&lt;/a&gt;'
```

Inside a text node the quotes are safe, so pass `quote=False` to keep the output smaller:

```pycon
>>> turbohtml.escape('He said "hi" & left', quote=False)
'He said "hi" &amp; left'
```

Turn HTML character references back into text, following the full HTML5 rules (named, numeric, and longest-match
references that omit the trailing semicolon):

```pycon
>>> turbohtml.unescape("caf&eacute; &amp; r&eacute;sum&eacute; &#127881;")
'café & résumé 🎉'
```

`escape` and `unescape` reproduce `html.escape` and `html.unescape` exactly, so turbohtml is a drop-in replacement on
hot paths.

## Performance

Measured on CPython 3.14 (release build) against the standard library's `html.escape` / `html.unescape`, via
`tox -e bench`:

| operation  | input                      | turbohtml | stdlib  | speedup |
| ---------- | -------------------------- | --------- | ------- | ------- |
| `escape`   | plain prose, no specials   | 0.35 µs   | 2.23 µs | 6.3×    |
| `escape`   | typical HTML markup        | 4.49 µs   | 10.5 µs | 2.3×    |
| `escape`   | special-dense              | 2.99 µs   | 26.5 µs | 8.9×    |
| `escape`   | non-ASCII prose (UCS-2)    | 0.92 µs   | 1.88 µs | 2.0×    |
| `escape`   | astral text (UCS-4)        | 2.58 µs   | 2.65 µs | 1.0×    |
| `unescape` | named references (dense)   | 18.1 µs   | 70.2 µs | 3.9×    |
| `unescape` | numeric references (dense) | 4.16 µs   | 76.8 µs | 18.5×   |
| `unescape` | mixed named + numeric      | 8.03 µs   | 35.2 µs | 4.4×    |
| `unescape` | prose, sparse references   | 3.93 µs   | 3.87 µs | ~1×     |
| `unescape` | non-ASCII with references  | 9.44 µs   | 35.2 µs | 3.7×    |

`escape` gains the most on text that needs little escaping — the SWAR scan skips eight safe bytes at a time — and
`unescape` gains the most on entity-heavy input, especially numeric references, where the standard library pays a Python
function call per match. Where the text is mostly plain, `unescape` ties the standard library, whose regex already
short-circuits and runs in C. Numbers vary with input and hardware; reproduce them with `tox -e bench`.

## Documentation

Full documentation, including tutorials, how-to guides, the API reference, and the design rationale, lives at
[turbohtml.readthedocs.io](https://turbohtml.readthedocs.io).

## License

`turbohtml` is released under the [MIT license](LICENSE).
