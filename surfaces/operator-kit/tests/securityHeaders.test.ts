import { IncomingMessage, ServerResponse } from "node:http";
import { Socket } from "node:net";
import { createEvent, type H3Event } from "h3";
import { describe, expect, it } from "vitest";
import {
  addCspNonceToHtml,
  applyOperatorSecurityHeaders,
  isImmutableOperatorAssetPath,
  OPERATOR_IMMUTABLE_CACHE_CONTROL,
  OPERATOR_PRIVATE_CACHE_CONTROL,
  operatorContentSecurityPolicy,
} from "../server/utils/securityHeaders";

function makeEvent(): { event: H3Event; res: ServerResponse } {
  const req = new IncomingMessage(new Socket());
  req.method = "GET";
  req.url = "/";
  const res = new ServerResponse(req);
  res.setHeader("x-powered-by", "Nuxt");
  return { event: createEvent(req, res), res };
}

describe("headers de segurança das superfícies de operador", () => {
  it("aplica a matriz estrita e cache privado sem expor a tecnologia", () => {
    const { event, res } = makeEvent();
    const nonce = applyOperatorSecurityHeaders(event);

    expect(nonce).toMatch(/^[A-Za-z0-9_-]{24}$/);
    expect(res.getHeader("cache-control")).toBe(OPERATOR_PRIVATE_CACHE_CONTROL);
    expect(res.getHeader("strict-transport-security")).toBe("max-age=31536000; includeSubDomains");
    expect(res.getHeader("x-content-type-options")).toBe("nosniff");
    expect(res.getHeader("x-frame-options")).toBe("DENY");
    expect(res.getHeader("referrer-policy")).toBe("no-referrer");
    expect(res.getHeader("cross-origin-opener-policy")).toBe("same-origin");
    expect(res.getHeader("cross-origin-resource-policy")).toBe("same-origin");
    expect(res.getHeader("permissions-policy")).toContain("camera=()");
    expect(res.getHeader("x-powered-by")).toBeUndefined();

    const csp = String(res.getHeader("content-security-policy"));
    expect(csp).toBe(operatorContentSecurityPolicy(nonce));
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain(`script-src 'self' 'nonce-${nonce}'`);
    expect(csp).not.toContain("script-src 'self' 'unsafe-inline'");
    expect(csp).not.toContain("default-src *");
  });

  it("coloca o mesmo nonce em scripts e estilos do HTML renderizado", () => {
    const html = '<style>.ok{color:green}</style><script>window.ok=1</script><script src="/entry.js"></script>';
    const secured = addCspNonceToHtml(html, "nonce-test");
    expect(secured).toBe(
      '<style nonce="nonce-test">.ok{color:green}</style><script nonce="nonce-test">window.ok=1</script><script nonce="nonce-test" src="/entry.js"></script>',
    );
    expect(addCspNonceToHtml(secured, "other")).toBe(secured);
  });

  it("reserva cache imutável somente aos assets versionados locais", () => {
    expect(isImmutableOperatorAssetPath("/_nuxt/entry.abc123.js")).toBe(true);
    expect(isImmutableOperatorAssetPath("/fonts/instrument-sans-latin-6219bc4b.woff2")).toBe(true);
    expect(isImmutableOperatorAssetPath("/api/v1/backstage/marketing/v2/")).toBe(false);
    expect(OPERATOR_IMMUTABLE_CACHE_CONTROL).toBe("public, max-age=31536000, immutable");
  });
});
