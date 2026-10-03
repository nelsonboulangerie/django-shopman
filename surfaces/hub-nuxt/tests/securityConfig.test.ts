import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { operatorBaselineContentSecurityPolicy } from "../../operator-kit/server/utils/operatorSecurity";

const surfaceRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const config = readFileSync(resolve(surfaceRoot, "nuxt.config.ts"), "utf8");

describe("Central: configuração segura de release", () => {
  it("ativa o envelope de headers do operator-kit no runtime privado", () => {
    expect(config).toContain("operatorSecurityHeaders: true");
  });

  it("abre só a exceção decidida: o ícone de cada app na origem dele", () => {
    expect(config).toContain('"img-src": ["https:"]');
    expect(config).not.toContain('"connect-src"');
    expect(config).not.toContain('"script-src"');
  });

  it("a política resultante mostra o ícone de outro app e mantém o resto fechado", () => {
    const csp = operatorBaselineContentSecurityPolicy({ "img-src": ["https:"] });
    expect(csp).toContain("img-src 'self' data: blob: https:");
    expect(csp).toContain("connect-src 'self';");
    expect(csp).toContain("frame-ancestors 'none'");
  });
});
