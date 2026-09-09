import { randomBytes } from "node:crypto";
import {
  removeResponseHeader,
  setResponseHeader,
  type H3Event,
} from "h3";

export const OPERATOR_PRIVATE_CACHE_CONTROL = "private, no-store";
export const OPERATOR_IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable";

const NONCE_BYTES = 18;

interface OperatorSecurityHeaderOptions {
  allowUnsafeInlineStyleElements?: boolean;
  cacheControl?: string;
  nonce?: string;
}

export function ensureOperatorCspNonce(event: H3Event): string {
  const existing = event.context.operatorCspNonce;
  if (typeof existing === "string" && existing) return existing;

  const nonce = randomBytes(NONCE_BYTES).toString("base64url");
  event.context.operatorCspNonce = nonce;
  return nonce;
}

export function operatorContentSecurityPolicy(
  nonce: string,
  allowUnsafeInlineStyleElements = false,
): string {
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "connect-src 'self'",
    "font-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "frame-src 'none'",
    "img-src 'self' data: https:",
    "manifest-src 'self'",
    "object-src 'none'",
    `script-src 'self' 'nonce-${nonce}'`,
    "style-src 'self'",
    allowUnsafeInlineStyleElements
      ? "style-src-elem 'self' 'unsafe-inline'"
      : `style-src-elem 'self' 'nonce-${nonce}'`,
    "style-src-attr 'unsafe-inline'",
    "worker-src 'self' blob:",
  ].join("; ");
}

export function operatorSecurityHeaders(
  nonce: string,
  cacheControl = OPERATOR_PRIVATE_CACHE_CONTROL,
  allowUnsafeInlineStyleElements = false,
): Readonly<Record<string, string>> {
  return {
    "cache-control": cacheControl,
    "content-security-policy": operatorContentSecurityPolicy(
      nonce,
      allowUnsafeInlineStyleElements,
    ),
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
    "referrer-policy": "no-referrer",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "x-dns-prefetch-control": "off",
    "x-frame-options": "DENY",
  };
}

export function applyOperatorSecurityHeaders(
  event: H3Event,
  options: OperatorSecurityHeaderOptions = {},
): string {
  const nonce = options.nonce || ensureOperatorCspNonce(event);
  const headers = operatorSecurityHeaders(
    nonce,
    options.cacheControl,
    options.allowUnsafeInlineStyleElements,
  );
  for (const [name, value] of Object.entries(headers)) {
    setResponseHeader(event, name, value);
  }
  removeResponseHeader(event, "x-powered-by");
  return nonce;
}

export function addCspNonceToHtml(html: string, nonce: string): string {
  return html.replace(
    /<(script|style)(?![^>]*\bnonce=)(\s|>)/gi,
    `<$1 nonce="${nonce}"$2`,
  );
}

export function isImmutableOperatorAssetPath(path: string): boolean {
  return path.startsWith("/_nuxt/") || path.startsWith("/fonts/");
}
