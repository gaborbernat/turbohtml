// Wrong-output oracle for turbohtml's JS minifier: run a program before and after minification and compare what it
// prints. Three lanes, each driving an upstream harness unmodified:
//   ufuzz    UglifyJS's random program generator, sandbox, false-positive filters and reducer (test/ufuzz/index.js)
//   uglify   UglifyJS's expect_stdout suite, which re-minifies every case under each option set (test/compress.js)
//   test262  test262-harness with a preprocessor that minifies each test before node runs it
// Usage: node oracle.js [ufuzz|uglify|test262 ...] --out DIR [--minutes N] [--seed S] [--update], from the fuzz-js tox
// env, whose Python (with turbohtml installed) must be the `python` on PATH.
// --update rewrites the uglify known-failure list and the test262 snapshot instead of checking against them.
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { parseArgs } = require("util");

const UGLIFY = path.join(__dirname, "UglifyJS");
const SHIM = path.join(__dirname, "uglify_shim.js");

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    out: { type: "string" },
    minutes: { type: "string", default: "2" },
    seed: { type: "string", default: String(crypto.randomInt(1, 2 ** 31)) },
    update: { type: "boolean", default: false },
  },
});
fs.mkdirSync(values.out, { recursive: true });
const lanes = { ufuzz, uglify, test262 };
const passed = (positionals.length ? positionals : Object.keys(lanes)).map((lane) => lanes[lane](values));
process.exitCode = passed.every(Boolean) ? 0 : 1;

function ufuzz({ out, minutes, seed }) {
  // negative control: a minifier that corrupts its output must be caught on the first program, or the chain is blind
  const control = runUfuzz(1, 1, { UFUZZ_CONTROL: "1" });
  if (control.status !== 1 || !control.stderr.includes("uglified result:"))
    throw new Error(`ufuzz missed the control:\n${control.stderr}`);
  const deadline = Date.now() + Number(minutes) * 60_000;
  const reports = [];
  let next = Number(seed);
  while (Date.now() < deadline) {
    const { status, stderr } = runUfuzz(next, 100);
    const last = Number(/^\/\/ ufuzz seed (\d+)$/m.exec(stderr)[1]);
    if (status !== 0) {
      reports.push(path.join(out, `ufuzz-${last}.txt`));
      fs.writeFileSync(reports.at(-1), stderr);
    }
    next = last + 1;
  }
  console.log(`ufuzz: seeds ${seed}..${next - 1}, ${reports.length} divergence(s)`);
  for (const report of reports) console.log(`  ${report}`);
  return reports.length === 0;
}

function runUfuzz(seed, iterations, env = {}) {
  return spawnSync(process.execPath, ["-r", SHIM, path.join(UGLIFY, "test", "ufuzz", "index.js"), `${iterations}`], {
    env: { ...process.env, ...env, UFUZZ_SEED: `${seed}` },
    encoding: "utf8",
    maxBuffer: 1 << 30,
    stdio: ["ignore", "ignore", "pipe"],
  });
}

function uglify({ out, update }) {
  const { stdout } = spawnSync(process.execPath, [path.join(UGLIFY, "test", "compress.js")], {
    cwd: UGLIFY,
    env: { ...process.env, NODE_OPTIONS: `--require ${SHIM}` },
    encoding: "utf8",
    maxBuffer: 1 << 30,
  });
  return compareKnown("uglify", reminifyFailures(stdout), "uglify_known_failures.txt", out, update);
}

// compress.js logs "--- <file>" per file, "    Running test [<name>]" per case and a "!!! ..." block per failure. Only
// the reminify blocks run turbohtml's output; the others check UglifyJS's own compressor against its goldens.
function reminifyFailures(log) {
  const failures = new Map();
  let file;
  let key;
  let match;
  for (const line of log.split("\n")) {
    if ((match = /^--- (\S+)$/.exec(line))) file = match[1];
    else if ((match = /^ {4}Running test \[(.+)]$/.exec(line))) key = `${file}:${match[1]}`;
    else if (/^!!! failed (input reminify|running reminified)/.test(line)) failures.set(key, `${key}\n${line}\n`);
    else if (failures.has(key)) failures.set(key, `${failures.get(key)}${line}\n`);
  }
  // compress.js gives each run 5 s; re-run a time-out with 10 s as ufuzz does, so a loaded machine flags no case
  const sandbox = require(path.join(UGLIFY, "test", "sandbox.js"));
  const timeout = /---INPUT---\n([\s\S]*?)\n---OPTIONS---[\s\S]*---OUTPUT---\n([\s\S]*?)\n---EXPECTED[\s\S]*timed out/;
  for (const [id, report] of failures) {
    const [, input, output] = timeout.exec(report) || [];
    if (input && sandbox.same_stdout(sandbox.run_code(input, false, 10_000), sandbox.run_code(output, false, 10_000))) {
      failures.delete(id);
    }
  }
  return failures;
}

// esbuild's uglify-tests.js and oxc's runtime snapshot: a recorded failure that starts passing fails the run too, so
// the list only ever shrinks and a fix is noticed. Each lane's failure reports land in <out>/<lane>.txt.
function compareKnown(lane, failures, listName, out, update) {
  const list = path.join(__dirname, listName);
  fs.writeFileSync(path.join(out, `${lane}.txt`), [...failures.values()].join("\n"));
  if (update) {
    fs.writeFileSync(list, `${[...failures.keys()].sort().join("\n")}\n`);
    return true;
  }
  const known = new Set(fs.readFileSync(list, "utf8").split("\n").filter(Boolean));
  const fresh = [...failures.keys()].filter((id) => !known.has(id));
  const fixed = [...known].filter((id) => !failures.has(id));
  console.log(`${lane}: ${failures.size} failing, ${fresh.length} new, ${fixed.length} now passing`);
  for (const id of fresh) console.log(`  new: ${id}`);
  for (const id of fixed) console.log(`  now passing (remove from ${listName}): ${id}`);
  return fresh.length === 0 && fixed.length === 0;
}

function test262({ out, update }) {
  const raw = new Map(runTest262([]).map(({ id, result }) => [id, result.pass]));
  const minified = runTest262(["--preprocessor", path.join(__dirname, "test262_preprocessor.js")]);
  const failures = minified.filter(({ id, result }) => !result.pass && raw.get(id));
  const reports = new Map(failures.map(({ id, result }) => [id, `${id}\n  ${result.message}\n`]));
  return compareKnown("test262", reports, "test262_snapshot.txt", out, update);
}

// test/intl402 and test/staging are left out: locale data and proposals exercise node, not syntax a minifier rewrites
function runTest262(extra) {
  const { stdout } = spawnSync(
    process.execPath,
    [
      require.resolve("test262-harness/bin/run.js"),
      ...extra,
      "--threads",
      `${os.availableParallelism()}`,
      "--reporter",
      "json",
      "--reporter-keys",
      "relative,scenario,result",
      ...["annexB", "built-ins", "language"].map((dir) => `test/${dir}/**/*.js`),
    ],
    { cwd: path.join(__dirname, "test262"), encoding: "utf8", maxBuffer: 1 << 30 },
  );
  return JSON.parse(stdout).map((test) => ({ id: `${test.relative} (${test.scenario})`, result: test.result }));
}
