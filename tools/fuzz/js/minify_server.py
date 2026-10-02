"""Answer JSON-line minify requests on stdin, so UglifyJS's Node harness can run turbohtml's JS minifier in-process."""

from __future__ import annotations

import json
import sys

from turbohtml.clean import JSMinify, Minify, minify, minify_js


def main() -> None:
    """Answer each request line until stdin closes, flushing every answer because the caller blocks on it."""
    for line in sys.stdin:
        request = json.loads(line)
        options = JSMinify(mangle=request["mangle"], fold=request["fold"])
        try:
            answer = {
                "code": minify(request["code"], Minify(minify_js=options))
                if request["html"]
                else minify_js(request["code"], options)
            }
        except ValueError as error:
            answer = {"error": str(error)}
        sys.stdout.write(f"{json.dumps(answer)}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
