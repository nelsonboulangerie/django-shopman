import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { operatorBaselineContentSecurityPolicy, operatorResponseHeaders } from "../../operator-kit/server/utils/operatorSecurity";

const surfaceRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const config = readFileSync(resolve(surfaceRoot, "nuxt.config.ts"), "utf8");

describe("Pedidos — configuração segura de release", () => {
  it("ativa o envelope de headers do operator-kit no runtime privado", () => {
    expect(config).toContain("operatorSecurityHeaders: true");
  });

  it("abre só as exceções decididas: foto de produto, agente do balcão e widget do iFood", () => {
    expect(config).toContain('"img-src": ["https:"]');
    expect(config).toContain('"connect-src": ["http://127.0.0.1:*", "http://localhost:*"]');
    // Chat com o cliente iFood (DEV-2026-019): o script e o iframe do iFood, por host
    // explícito, e nada mais.
    expect(config).toContain('"script-src": ["https://widgets.ifood.com.br"]');
    expect(config).toContain('"frame-src": ["https://embeddables.ifood.com.br"]');
    expect(config.match(/"script-src"/g)).toHaveLength(1);
    expect(config.match(/"frame-src"/g)).toHaveLength(1);
  });

  it("abre só a localização (G18, fora da loja), e só para a própria origem", () => {
    expect(config).toContain('operatorPermissionsAllow: { geolocation: "self" }');
    const headers = operatorResponseHeaders({ pathname: "/", secure: true, permissionsAllow: { geolocation: "self" } });
    expect(headers["Permissions-Policy"]).toBe(
      "browsing-topics=(), camera=(), geolocation=(self), microphone=(), payment=(), screen-wake-lock=(self), usb=()",
    );
  });

  it("a política resultante carrega a foto, fala com o agente e enquadra só o iFood", () => {
    const csp = operatorBaselineContentSecurityPolicy({
      "img-src": ["https:"],
      "connect-src": ["http://127.0.0.1:*", "http://localhost:*"],
      "script-src": ["https://widgets.ifood.com.br"],
      "frame-src": ["https://embeddables.ifood.com.br"],
    });
    expect(csp).toContain("img-src 'self' data: blob: https:");
    expect(csp).toContain("connect-src 'self' http://127.0.0.1:* http://localhost:*");
    expect(csp).toContain("script-src 'self' 'unsafe-inline' https://widgets.ifood.com.br;");
    expect(csp).toContain("frame-src https://embeddables.ifood.com.br;");
    expect(csp).toContain("frame-ancestors 'none'");
  });
});
