// test262-harness --preprocessor: minify each compiled test (harness includes plus the test, per scenario) with the
// full turbohtml pipeline and hand the harness the minified text, so the code that runs is the code that was minified.
const { minify } = require("./turbohtml_minify.js");

module.exports = function (test) {
  // turbohtml parses the script goal only; its module syntax error is documented, not a divergence
  if (test.attrs.flags.module) return false;
  const minified = minify(test.contents, { mangle: true, fold: true });
  if (minified.error === undefined) {
    test.contents = minified.code;
    return true;
  }
  // a rejected early-error test counts as the parse-phase SyntaxError it expects; any other rejection fails the test
  const name = test.attrs.negative?.phase === "parse" ? "SyntaxError" : "MinifyError";
  const { message } = minified.error;
  test.result = { stdout: "", stderr: `${name}: ${message}\n`, error: { name, message } };
  return true;
};
