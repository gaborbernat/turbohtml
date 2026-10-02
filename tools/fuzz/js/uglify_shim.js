// Preloaded (`node -r`) into UglifyJS's own fuzzer (test/ufuzz/index.js) and test runner (test/compress.js) so they run
// unmodified against turbohtml: their option sets become the JSMinify sweep, every minify() call that carries one goes
// to turbohtml, and the rest (ufuzz's beautifier for its reports) stays with UglifyJS. Their false-positive filters,
// reducer and "suspicious options" report then apply to turbohtml as they do to UglifyJS.
const path = require("path");
const { isMainThread } = require("worker_threads");

const UGLIFY = path.join(__dirname, "UglifyJS");

// NODE_OPTIONS also reaches the synckit worker and the sandbox's child processes, which must stay untouched
if (isMainThread && /UglifyJS[/\\]test[/\\](compress|ufuzz[/\\]index)\.js$/.test(process.argv[1] ?? "")) {
  const turbohtml = require("./turbohtml_minify.js");
  const sandbox = require(path.join(UGLIFY, "test", "sandbox.js"));
  const minify = process.env.UFUZZ_CONTROL
    ? (code, options) => corruptReport(turbohtml.minify(code, options))
    : turbohtml.minify;
  require.cache[path.join(UGLIFY, "test", "ufuzz", "options.json")] = { loaded: true, exports: optionSets() };
  for (const entry of ["tools/node.js", "test/node.js"]) {
    const uglify = require(path.join(UGLIFY, entry));
    const original = uglify.minify;
    // turbohtml parses the script goal only, so hand it the script the sandbox runs: import/export rewritten its way
    uglify.minify = (code, options) =>
      options.turbohtml
        ? minify(sandbox.patch_module_statements(code, false), options.turbohtml)
        : original(code, options);
    // log_suspects() flips each key of the default options and reports the flips that change the outcome
    uglify.default_options = () => ({ turbohtml: { mangle: true, fold: true } });
  }
  if (process.env.UFUZZ_SEED) seedGenerator(Number(process.env.UFUZZ_SEED));
}

// oracle.js's negative control: turbohtml's output with ufuzz's final report line altered must be flagged as divergent
function corruptReport(answer) {
  return answer.error
    ? answer
    : { code: answer.code.replace(/console\.log\(null,(?!.*console\.log)/s, "console.log(0,") };
}

function optionSets() {
  return [
    { mangle: true, fold: true },
    { mangle: false, fold: true },
    { mangle: true, fold: false },
    { mangle: false, fold: false },
    { mangle: true, fold: true, rounds: 2 },
    { mangle: true, fold: true, rounds: 3 },
    { mangle: true, fold: true, html: true },
  ].map((options) => ({ module: false, turbohtml: options }));
}

// ufuzz draws from crypto.randomBytes with no seed; swap in terser's seedable LCG (terser test/ufuzz.js makeRng) and
// reseed at each "<round> of <total>" progress line, so program N is a pure function of seed + N - 1. The progress line
// itself is dropped from the log, and the seed of the last program is printed on exit to label a failure report.
function seedGenerator(base) {
  const modulus = 2 ** 35 - 31;
  let state = base;
  let seed = base;
  require("crypto").randomBytes = (size) => {
    const bytes = Buffer.alloc(size);
    for (let index = 0; index < size; index++) {
      bytes[index] = Math.floor((256 * (state = (state * 185852) % modulus)) / modulus);
    }
    return bytes;
  };
  const write = process.stdout.write;
  process.stdout.write = function (chunk, ...rest) {
    const progress = /^(\d+) of /.exec(chunk);
    if (!progress) return write.call(this, chunk, ...rest);
    state = seed = base + Number(progress[1]) - 1;
    return true;
  };
  process.on("exit", () => process.stderr.write(`// ufuzz seed ${seed}\n`));
}
