import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  OPERATOR_CONTENT_SECURITY_POLICY,
  operatorResponseHeaders,
} from "../../operator-kit/server/utils/operatorSecurity";

const surfaceRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const config = readFileSync(resolve(surfaceRoot, "nuxt.config.ts"), "utf8");

describe("Compras: configuração segura de release", () => {
  it("ativa o envelope de headers do operator-kit no runtime privado", () => {
    expect(config).toContain("operatorSecurityHeaders: true");
  });

  it("abre só a câmera, decidida pelo dono, e só para a própria origem", () => {
    expect(config).toContain('operatorPermissionsAllow: { camera: "self" }');
    const headers = operatorResponseHeaders({
      pathname: "/",
      secure: true,
      permissionsAllow: { camera: "self" },
    });
    expect(headers["Permissions-Policy"]).toBe(
      "browsing-topics=(), camera=(self), geolocation=(), microphone=(), payment=(), screen-wake-lock=(self), usb=()",
    );
  });

  it("não declara exceção de CSP: a política é a de base", () => {
    expect(config).not.toContain("operatorCspAllow");
    const headers = operatorResponseHeaders({ pathname: "/", secure: true, permissionsAllow: { camera: "self" } });
    expect(headers["Content-Security-Policy"]).toBe(OPERATOR_CONTENT_SECURITY_POLICY);
    expect(OPERATOR_CONTENT_SECURITY_POLICY).toContain("img-src 'self' data: blob:");
  });
});
