// synckit worker behind turbohtml_minify.js: one long-lived Python process serves every request, because UglifyJS's
// fuzzer, reducer and test runner call minify() synchronously thousands of times and an interpreter per call costs
// more than the program run it is compared against.
const path = require("path");
const readline = require("readline");
const { spawn } = require("child_process");
const parse5 = require("parse5");
const { runAsWorker } = require("synckit");

const pending = [];
let server = startServer();

runAsWorker(async (code, options) => {
  for (let round = 0; round < options.rounds; round++) {
    const answer = await request({
      code: options.html ? `<script>${code}</script>` : code,
      mangle: options.mangle,
      fold: options.fold,
      html: options.html,
    });
    if (answer.error !== undefined) return answer;
    code = options.html ? scriptText(answer.code) : answer.code;
  }
  return { code };
});

// a minifier crash kills the server, and a hang gets it killed: answer the request in flight with that and start a
// fresh server for the next
function startServer() {
  const child = spawn("python", [path.join(__dirname, "minify_server.py")], { stdio: ["pipe", "pipe", "inherit"] });
  readline.createInterface({ input: child.stdout }).on("line", (line) => {
    const answer = JSON.parse(line);
    pending.shift()(answer.error === undefined ? answer : { error: { name: "ValueError", message: answer.error } });
  });
  child.on("exit", (code, signal) => {
    const message = child.hung ? "minifier ran past 10 s" : `minifier process died with ${signal || `exit ${code}`}`;
    for (const resolve of pending.splice(0)) resolve({ error: { name: "MinifierCrash", message } });
    server = startServer();
  });
  return child;
}

function request(message) {
  const child = server;
  const timer = setTimeout(() => (child.hung = child.kill()), 10_000);
  return new Promise((resolve) => {
    pending.push((answer) => {
      clearTimeout(timer);
      resolve(answer);
    });
    child.stdin.write(`${JSON.stringify(message)}\n`);
  });
}

// parse5, not turbohtml, reads the script back: a serializer bug that turbohtml's own parser undoes would cancel out
function scriptText(html) {
  const scripts = [];
  (function walk(node) {
    if (node.tagName === "script") scripts.push(node.childNodes.map((child) => child.value).join(""));
    for (const child of node.childNodes || []) walk(child);
  })(parse5.parse(html));
  return scripts.join("\n");
}
