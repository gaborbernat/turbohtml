Minifying CSS whose values nest many functions, such as long ``var()`` fallback chains, no longer rescans the arguments
of every nested call, so those stylesheets minify about three times faster.
