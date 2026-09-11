import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const appRoot = fileURLToPath(new URL("../", import.meta.url));
const config = readFileSync(new URL("../nuxt.config.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/assets/css/tailwind.css", import.meta.url), "utf8");
const securityMiddleware = readFileSync(
  new URL("../server/middleware/00-security.ts", import.meta.url),
  "utf8",
);
const cspPlugin = readFileSync(
  new URL("../server/plugins/cspNonce.ts", import.meta.url),
  "utf8",
);

describe("entrega local de fontes do Marketing", () => {
  it("não configura provider ou endpoint de fontes de terceiros", () => {
    expect(config).not.toContain("@nuxt/fonts");
    expect(config).not.toContain("provider: 'google'");
    expect(css).not.toMatch(/fonts\.(?:googleapis|gstatic)\.com/);
    expect(css).not.toMatch(/https?:\/\//);
  });

  it("versiona todos os webfonts citados pelo CSS e a licença", () => {
    const urls = [...css.matchAll(/url\("(\/fonts\/[^"]+\.woff2)"\)/g)].map((match) => match[1]);
    expect(urls).toEqual([
      "/fonts/instrument-sans-latin-ext-21fac8da.woff2",
      "/fonts/instrument-sans-latin-6219bc4b.woff2",
      "/fonts/fira-code-latin-ext-e085302e.woff2",
      "/fonts/fira-code-latin-5c18638f.woff2",
    ]);
    for (const url of urls) expect(existsSync(`${appRoot}/public${url}`)).toBe(true);
    expect(readFileSync(`${appRoot}/public/fonts/OFL.txt`, "utf8")).toContain("SIL OPEN FONT LICENSE Version 1.1");
  });

  it("permite o style HMR somente pelo branch compile-time de desenvolvimento", () => {
    expect(securityMiddleware).toContain(
      "allowUnsafeInlineStyleElements: import.meta.dev",
    );
    expect(cspPlugin).toContain("import.meta.dev");
    expect(securityMiddleware).not.toContain("script-src 'self' 'unsafe-inline'");
    expect(cspPlugin).not.toContain("script-src 'self' 'unsafe-inline'");
  });
});
