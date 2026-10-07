const fs = require("node:fs");
const reduce = require("./js_reduce");

function readLine() {
  const bytes = [];
  const byte = Buffer.alloc(1);
  while (fs.readSync(0, byte, 0, 1, null)) {
    if (byte[0] === 10) return Buffer.from(bytes).toString("utf8");
    bytes.push(byte[0]);
  }
  throw new Error("reducer parent closed its input");
}

function send(kind, text) {
  process.stdout.write(JSON.stringify({kind, text}) + "\n");
}

const {text, budget} = JSON.parse(readLine());
send("done", reduce(text, candidate => {
  send("candidate", candidate);
  return JSON.parse(readLine());
}, budget));
