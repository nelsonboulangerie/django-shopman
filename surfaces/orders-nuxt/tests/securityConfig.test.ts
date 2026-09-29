import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { operatorContentSecurityPolicy } from "../../operator-kit/server/utils/operatorSecurity";

const surfaceRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const config = readFileSync(resolve(surfaceRoot, "nuxt.config.ts"), "utf8");

describe("Pedidos — configuração segura de release", () => {
  it("ativa o envelope de headers do operator-kit no runtime privado", () => {
    expect(config).toContain("operatorSecurityHeaders: true");
  });

  it("abre só as duas exceções decididas: foto de produto e agente do balcão", () => {
    expect(config).toContain('"img-src": ["https:"]');
    expect(config).toContain('"connect-src": ["http://127.0.0.1:*", "http://localhost:*"]');
    expect(config).not.toContain('"script-src"');
  });

  it("a política resultante carrega a foto e fala com o agente, e nada além", () => {
    const csp = operatorContentSecurityPolicy({
      "img-src": ["https:"],
      "connect-src": ["http://127.0.0.1:*", "http://localhost:*"],
    });
    expect(csp).toContain("img-src 'self' data: blob: https:");
    expect(csp).toContain("connect-src 'self' http://127.0.0.1:* http://localhost:*");
    expect(csp).toContain("frame-ancestors 'none'");
  });
});
