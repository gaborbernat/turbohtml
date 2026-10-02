// Synchronous turbohtml minify_js / inline-<script> minify for Node callers that cannot await (UglifyJS's harness).
// Options: { mangle, fold, html, rounds }; returns UglifyJS's minify() shape, { code } or { error }.
const { createSyncFn } = require("synckit");

const minifySync = createSyncFn(require.resolve("./minify_worker.js"));

exports.minify = function (code, options) {
  const answer = minifySync(code, { rounds: 1, html: false, ...options });
  if (answer.error === undefined) return answer;
  // named ValueError or MinifierCrash, never SyntaxError: UglifyJS's reducer gives up on a SyntaxError from minify()
  const error = new Error(answer.error.message);
  error.name = answer.error.name;
  error.stack = `${error.name}: ${error.message}`;
  return { error };
};
