// Mock builder: compiles Tailwind v4 with the REAL operator-kit tokens, inlines
// Lucide icons, renders each mock HTML to PNG.
// usage: node build.mjs [name ...]   (no args = all *.html in ./src)
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const ROOT = "/home/user/django-shopman/.claude/worktrees/ux-reform-plan/surfaces";
const NM = `${ROOT}/pos-nuxt/node_modules`;
const req = createRequire(`${NM}/`);
const { compile } = await import(`${NM}/@tailwindcss/node/dist/index.mjs`);
const { Scanner } = req("@tailwindcss/oxide");
const { chromium } = await import(`${NM}/playwright/index.mjs`);
const lucide = JSON.parse(fs.readFileSync(`${NM}/@iconify-json/lucide/icons.json`, "utf8"));

const HERE = path.dirname(new URL(import.meta.url).pathname);
const SRC = `${HERE}/src`;
const OUT = `${HERE}/out`;
fs.mkdirSync(OUT, { recursive: true });

function icon(name, cls) {
  const ic = lucide.icons[name] || lucide.icons[lucide.aliases?.[name]?.parent];
  if (!ic) { console.warn("missing icon", name); return `<span class="${cls}">?</span>`; }
  const w = ic.width || lucide.width || 24, h = ic.height || lucide.height || 24;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" class="${cls || "size-4"}" aria-hidden="true">${ic.body}</svg>`;
}

const fontsCss = fs.readFileSync(`${HERE}/fonts/fonts.local.css`, "utf8");
const kitBase = `${ROOT}/operator-kit/app/assets/css/operator-base.css`;
const shared = fs.existsSync(`${SRC}/_shared.css`) ? fs.readFileSync(`${SRC}/_shared.css`, "utf8") : "";

const inputCss = `@import "tailwindcss";
@import "tw-animate-css";
@import "${kitBase}";
${shared}`;

const names = process.argv.slice(2);
const files = fs.readdirSync(SRC).filter((f) => f.endsWith(".html") && !f.startsWith("_"))
  .filter((f) => !names.length || names.includes(f.replace(/\.html$/, "")));

// expand icons + partials first so the scanner sees final markup
const partials = {};
for (const f of fs.readdirSync(SRC).filter((f) => f.startsWith("_") && f.endsWith(".html"))) {
  partials[f.slice(1, -5)] = fs.readFileSync(`${SRC}/${f}`, "utf8");
}
function expand(html, vars = {}) {
  // {{> partial key=value key2="a b"}}
  html = html.replace(/\{\{>\s*([\w-]+)([^}]*)\}\}/g, (_, p, args) => {
    const v = { ...vars };
    for (const m of args.matchAll(/(\w+)="([^"]*)"/g)) v[m[1]] = m[2];
    return expand(partials[p] || `<!-- missing ${p} -->`, v);
  });
  html = html.replace(/\{\{(\w+)\}\}/g, (_, k) => vars[k] ?? "");
  html = html.replace(/<i\s+data-i="([\w-]+)"(?:\s+class="([^"]*)")?\s*><\/i>/g, (_, n, c) => icon(n, c));
  return html;
}
const expanded = files.map((f) => ({ f, html: expand(fs.readFileSync(`${SRC}/${f}`, "utf8")) }));

const compiler = await compile(inputCss, {
  base: `${ROOT}/pos-nuxt/app/assets/css`,
  onDependency: () => {},
});
const scanner = new Scanner({ sources: [] });
const candidates = new Set();
for (const { html } of expanded) {
  for (const c of scanner.scanFiles([{ content: html, extension: "html" }])) candidates.add(c);
  for (const c of new Scanner({}).getCandidatesWithPositions({ content: html, extension: "html" })) candidates.add(c.candidate);
}
const css = compiler.build([...candidates]);

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
for (const { f, html } of expanded) {
  const m = html.match(/<meta name="viewport-size" content="(\d+)x(\d+)(?:@(\d))?"/);
  const [w, h, dpr] = m ? [+m[1], +m[2], +(m[3] || 1)] : [1440, 900, 1];
  const full = /data-full-page/.test(html);
  const doc = html.replace("</head>", `<style>${fontsCss}\n${css}</style></head>`);
  const outHtml = `${OUT}/${f}`;
  fs.writeFileSync(outHtml, doc);
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
  const page = await ctx.newPage();
  await page.goto(`file://${outHtml}`);
  await page.waitForTimeout(400);
  const base = f.replace(/\.html$/, "");
  await page.screenshot({ path: `${OUT}/${base}.annotated.png`, fullPage: true });
  await page.addStyleTag({ content: ".pin,.legend,.note{display:none!important}" });
  await page.screenshot({ path: `${OUT}/${base}.png`, clip: { x: 0, y: 0, width: w, height: h } });
  await ctx.close();
  console.log("rendered", f, `${w}x${h}`);
}
await browser.close();
