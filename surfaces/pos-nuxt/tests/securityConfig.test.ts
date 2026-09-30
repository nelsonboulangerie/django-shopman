import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  OPERATOR_PERMISSIONS_POLICY,
  operatorBaselineContentSecurityPolicy,
  operatorResponseHeaders,
} from "../../operator-kit/server/utils/operatorSecurity";

const surfaceRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const config = readFileSync(resolve(surfaceRoot, "nuxt.config.ts"), "utf8");

// Espelho do `operatorCspAllow` do nuxt.config: se um mudar sem o outro, o teste
// de texto abaixo reprova.
const POS_CSP_ALLOW = {
  "script-src": ["https://maps.googleapis.com"],
  "connect-src": [
    "https://maps.googleapis.com",
    "https://places.googleapis.com",
    "https://viacep.com.br",
    "http://127.0.0.1:*",
    "http://localhost:*",
  ],
  "img-src": ["https:"],
};

describe("PDV: configuração segura de release", () => {
  it("ativa o envelope de headers do operator-kit no runtime privado", () => {
    expect(config).toContain("operatorSecurityHeaders: true");
  });

  it("abre só as exceções decididas: Maps, ViaCEP, foto de produto e agente do balcão", () => {
    expect(config).toContain('"script-src": ["https://maps.googleapis.com"]');
    for (const source of POS_CSP_ALLOW["connect-src"]) expect(config).toContain(`"${source}"`);
    expect(config).toContain('"img-src": ["https:"]');
    expect(config).not.toContain('"font-src"');
    expect(config).not.toContain('"media-src"');
    expect(config).not.toContain("unsafe-eval");
  });

  it("não abre recurso do navegador: a Permissions-Policy é a de base", () => {
    expect(config).not.toContain("operatorPermissionsAllow");
    const headers = operatorResponseHeaders({ pathname: "/", secure: true, cspAllow: POS_CSP_ALLOW });
    expect(headers["Permissions-Policy"]).toBe(OPERATOR_PERMISSIONS_POLICY);
    expect(headers["Permissions-Policy"]).toContain("geolocation=()");
  });

  it("a política resultante carrega o Maps e fala com ViaCEP e o agente, e nada além", () => {
    const csp = operatorBaselineContentSecurityPolicy(POS_CSP_ALLOW);
    expect(csp).toContain("script-src 'self' 'unsafe-inline' https://maps.googleapis.com;");
    expect(csp).toContain(
      "connect-src 'self' https://maps.googleapis.com https://places.googleapis.com https://viacep.com.br http://127.0.0.1:* http://localhost:*;",
    );
    expect(csp).toContain("img-src 'self' data: blob: https:;");
    expect(csp).toContain("font-src 'self' data:;");
    expect(csp).toContain("frame-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
  });
});
