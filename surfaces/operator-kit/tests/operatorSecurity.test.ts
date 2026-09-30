import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  mergeVaryHeader,
  OPERATOR_CONTENT_SECURITY_POLICY,
  OPERATOR_PERMISSIONS_POLICY,
  operatorBaselineContentSecurityPolicy,
  operatorBaselinePermissionsPolicy,
  operatorResponseHeaders,
} from "../server/utils/operatorSecurity";

const middlewareSource = readFileSync(
  fileURLToPath(new URL("../server/middleware/operator-security.ts", import.meta.url)),
  "utf8",
);

describe("operator-kit — borda HTTP segura", () => {
  it("instala o middleware no layer compartilhado", () => {
    expect(middlewareSource).toMatch(/applyOperatorBaselineSecurityHeaders\(event[,)]/);
  });

  it("fecha frame/object e envia os headers defensivos em documentos privados", () => {
    const headers = operatorResponseHeaders({ pathname: "/reports", secure: true });

    expect(OPERATOR_CONTENT_SECURITY_POLICY).toContain("frame-ancestors 'none'");
    expect(OPERATOR_CONTENT_SECURITY_POLICY).toContain("object-src 'none'");
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["Referrer-Policy"]).toBe("no-referrer");
    expect(headers["Permissions-Policy"]).toContain("camera=()");
    expect(headers["Strict-Transport-Security"]).toMatch(/^max-age=31536000/);
    expect(headers["Cache-Control"]).toBe("private, no-store, max-age=0");
    expect(headers.Vary).toBe("Cookie");
  });

  it("não emite HSTS em HTTP e não destrói o cache de assets compilados", () => {
    const documentHeaders = operatorResponseHeaders({ pathname: "/", secure: false });
    const assetHeaders = operatorResponseHeaders({ pathname: "/_nuxt/app.hash.js", secure: true });

    expect(documentHeaders["Strict-Transport-Security"]).toBeUndefined();
    expect(assetHeaders["Content-Security-Policy"]).toBe(OPERATOR_CONTENT_SECURITY_POLICY);
    expect(assetHeaders["Cache-Control"]).toBeUndefined();
    expect(assetHeaders.Vary).toBeUndefined();
  });

  it("preserva e deduplica Vary do upstream sem enfraquecer Cookie", () => {
    expect(mergeVaryHeader("Accept-Encoding, Cookie", ["cookie", "Accept-Language"])).toBe(
      "Accept-Encoding, Cookie, Accept-Language",
    );
    expect(mergeVaryHeader("Accept-Encoding", "*")).toBe("*");
  });
});

describe("operator-kit — exceção de CSP por app e por diretiva", () => {
  it("sem exceção declarada, a política é exatamente a de base", () => {
    expect(operatorBaselineContentSecurityPolicy()).toBe(OPERATOR_CONTENT_SECURITY_POLICY);
    expect(operatorBaselineContentSecurityPolicy({})).toBe(OPERATOR_CONTENT_SECURITY_POLICY);
  });

  it("acrescenta a origem só na diretiva declarada e mantém o resto fechado", () => {
    const csp = operatorBaselineContentSecurityPolicy({
      "img-src": ["https:"],
      "connect-src": ["http://127.0.0.1:*", "http://localhost:*"],
    });

    expect(csp).toContain("img-src 'self' data: blob: https:");
    expect(csp).toContain("connect-src 'self' http://127.0.0.1:* http://localhost:*");
    expect(csp).toContain("script-src 'self' 'unsafe-inline'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("default-src 'self';");
  });

  it("recusa diretiva que não aceita exceção", () => {
    for (const directive of ["default-src", "style-src", "worker-src", "frame-src", "form-action", "base-uri"]) {
      expect(() =>
        operatorBaselineContentSecurityPolicy({ [directive]: ["https://cdn.example.com"] } as never),
      ).toThrow(new RegExp(directive));
    }
    expect(() =>
      operatorBaselineContentSecurityPolicy({ "frame-ancestors": ["https:"] } as never),
    ).toThrow(/frame-ancestors/);
  });

  it("recusa origem que desliga a política", () => {
    for (const source of [
      "*",
      "'unsafe-eval'",
      "http:",
      "data:",
      "http://192.168.0.10:47811",
      "https://*",
      "https://*.com",
      "https://*.com.br",
      "https://*.co.uk",
      "https://*.*.example.com",
      "https://maps.*.com",
      "http://*.example.com",
    ]) {
      expect(() => operatorBaselineContentSecurityPolicy({ "img-src": [source] })).toThrow();
    }
  });

  it("o header do documento usa a política com a exceção do app", () => {
    const headers = operatorResponseHeaders({
      pathname: "/catalog",
      secure: true,
      cspAllow: { "img-src": ["https://img.nelsonboulangerie.com.br"] },
    });
    expect(headers["Content-Security-Policy"]).toContain(
      "img-src 'self' data: blob: https://img.nelsonboulangerie.com.br",
    );
  });

  it("aceita curinga de subdomínio sobre domínio fixo nas diretivas extensíveis", () => {
    const csp = operatorBaselineContentSecurityPolicy({
      "img-src": ["https://*.gstatic.com"],
      "connect-src": ["https://*.googleapis.com", "https://*.nelsonboulangerie.com.br"],
      "font-src": ["https://*.gstatic.com"],
    });
    expect(csp).toContain("img-src 'self' data: blob: https://*.gstatic.com");
    expect(csp).toContain("connect-src 'self' https://*.googleapis.com https://*.nelsonboulangerie.com.br");
    expect(csp).toContain("font-src 'self' data: https://*.gstatic.com");
  });

  it("o middleware repassa a exceção declarada no runtimeConfig", () => {
    expect(middlewareSource).toContain("config.operatorCspAllow");
  });
});

describe("operator-kit: exceção de script-src, mais estreita que as outras", () => {
  it("aceita host https explícito e curinga de subdomínio de domínio fixo", () => {
    const csp = operatorBaselineContentSecurityPolicy({
      "script-src": ["https://maps.googleapis.com", "https://*.gstatic.com"],
    });
    expect(csp).toContain("script-src 'self' 'unsafe-inline' https://maps.googleapis.com https://*.gstatic.com;");
    expect(csp).not.toMatch(/script-src[^;]*unsafe-eval/);
    expect(csp).toContain("frame-ancestors 'none'");
  });

  it("recusa em script-src o que as outras diretivas aceitam e o que desliga a política", () => {
    for (const source of [
      "https:",
      "*",
      "'unsafe-eval'",
      "'unsafe-inline'",
      "'unsafe-hashes'",
      "'wasm-unsafe-eval'",
      "http:",
      "http://maps.googleapis.com",
      "http://127.0.0.1:*",
      "http://localhost:47811",
      "https://localhost",
      "https://*",
      "https://*.com",
      "https://*.com.br",
      "data:",
      "blob:",
    ]) {
      expect(() => operatorBaselineContentSecurityPolicy({ "script-src": [source] }), source).toThrow(
        /script-src/,
      );
    }
  });
});

describe("operator-kit: exceção de Permissions-Policy por app e por recurso", () => {
  it("sem exceção declarada, o header é byte a byte o de base", () => {
    const base =
      "browsing-topics=(), camera=(), geolocation=(), microphone=(), payment=(), screen-wake-lock=(self), usb=()";
    expect(OPERATOR_PERMISSIONS_POLICY).toBe(base);
    expect(operatorBaselinePermissionsPolicy()).toBe(base);
    expect(operatorBaselinePermissionsPolicy(null)).toBe(base);
    expect(operatorBaselinePermissionsPolicy({})).toBe(base);
    expect(operatorResponseHeaders({ pathname: "/", secure: true })["Permissions-Policy"]).toBe(base);
  });

  it("abre só o recurso declarado, e só para a própria origem", () => {
    expect(operatorBaselinePermissionsPolicy({ camera: "self" })).toBe(
      "browsing-topics=(), camera=(self), geolocation=(), microphone=(), payment=(), screen-wake-lock=(self), usb=()",
    );
    const headers = operatorResponseHeaders({
      pathname: "/",
      secure: true,
      permissionsAllow: { camera: "self" },
    });
    expect(headers["Permissions-Policy"]).toContain("camera=(self)");
    expect(headers["Permissions-Policy"]).toContain("geolocation=()");
    expect(headers["Permissions-Policy"]).toContain("microphone=()");
  });

  it("recusa recurso fora da lista de base", () => {
    for (const feature of ["fullscreen", "autoplay", "clipboard-read", "serial"]) {
      expect(() => operatorBaselinePermissionsPolicy({ [feature]: "self" } as never)).toThrow(
        new RegExp(feature),
      );
    }
  });

  it("recusa valor que não seja self", () => {
    for (const value of ["*", "https://example.com", "(self)", "self https://example.com", "", true]) {
      expect(() => operatorBaselinePermissionsPolicy({ camera: value } as never), String(value)).toThrow(
        /camera/,
      );
    }
  });

  it("o middleware repassa a exceção declarada no runtimeConfig", () => {
    expect(middlewareSource).toContain("config.operatorPermissionsAllow");
  });
});
