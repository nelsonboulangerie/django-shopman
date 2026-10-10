// Downloads woff2 referenced by fonts.css and rewrites to local files.
import fs from "node:fs";
const dir = new URL("./fonts/", import.meta.url).pathname;
let css = fs.readFileSync(dir + "fonts.css", "utf8");
const urls = [...new Set(css.match(/https:\/\/[^)]+\.woff2/g))];
for (const [i, u] of urls.entries()) {
  const name = `f${i}.woff2`;
  const res = await fetch(u);
  fs.writeFileSync(dir + name, Buffer.from(await res.arrayBuffer()));
  css = css.split(u).join(`file://${dir}${name}`);
}
fs.writeFileSync(dir + "fonts.local.css", css);
console.log("fonts", urls.length);
