import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_CONTENT_SECURITY_POLICY } from "../../operator-kit/server/utils/operatorSecurity";

const surfaceRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const config = readFileSync(resolve(surfaceRoot, "nuxt.config.ts"), "utf8");

describe("B.I.: configuração segura de release", () => {
  it("ativa o envelope de headers do operator-kit no runtime privado", () => {
    expect(config).toContain("operatorSecurityHeaders: true");
  });

  it("não declara exceção de CSP: tudo o que o app carrega vem da própria origem", () => {
    expect(config).not.toMatch(/operatorCspAllow\s*:/);
    expect(config).not.toContain('"script-src"');
  });

  it("a política resultante é a de base do kit, fechada para outras origens", () => {
    expect(OPERATOR_CONTENT_SECURITY_POLICY).toContain("connect-src 'self';");
    expect(OPERATOR_CONTENT_SECURITY_POLICY).toContain("img-src 'self' data: blob:;");
    expect(OPERATOR_CONTENT_SECURITY_POLICY).toContain("frame-ancestors 'none'");
  });
});
