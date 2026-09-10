let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", () => {
  if (process.argv[2] === "parse5") {
    const parse5 = require("parse5");
    const document = parse5.parse(input);
    const html = document.childNodes.find((node) => node.tagName === "html");
    process.stdout.write(parse5.serialize(html.childNodes.find((node) => node.tagName === "body")));
  } else {
    const { JSDOM } = require("jsdom");
    const dom = new JSDOM(input);
    process.stdout.write(dom.window.document.body.innerHTML);
    dom.window.close();
  }
});
