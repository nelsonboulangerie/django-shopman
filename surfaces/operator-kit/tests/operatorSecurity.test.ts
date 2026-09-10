import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  mergeVaryHeader,
  OPERATOR_CONTENT_SECURITY_POLICY,
  operatorResponseHeaders,
} from "../server/utils/operatorSecurity";

const middlewareSource = readFileSync(
  fileURLToPath(new URL("../server/middleware/operator-security.ts", import.meta.url)),
  "utf8",
);

describe("operator-kit — borda HTTP segura", () => {
  it("instala o middleware no layer compartilhado", () => {
    expect(middlewareSource).toContain("applyOperatorSecurityHeaders(event)");
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
