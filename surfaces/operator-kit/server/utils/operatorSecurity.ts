import {
  getRequestHeader,
  getRequestURL,
  getResponseHeader,
  setResponseHeaders,
  type H3Event,
} from "h3";

const ONE_YEAR_SECONDS = 31_536_000;

export const OPERATOR_CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "connect-src 'self'",
  "font-src 'self' data:",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "frame-src 'none'",
  "img-src 'self' data: blob:",
  "manifest-src 'self'",
  "media-src 'self' blob:",
  "object-src 'none'",
  // Nuxt serializa o payload de hidratação em script inline. Nonces devem
  // substituir unsafe-inline num WP de CSP dinâmica; eval e origens externas
  // permanecem fechados desde já.
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "worker-src 'self' blob:",
].join("; ");

export const OPERATOR_PERMISSIONS_POLICY = [
  "browsing-topics=()",
  "camera=()",
  "geolocation=()",
  "microphone=()",
  "payment=()",
  "screen-wake-lock=(self)",
  "usb=()",
].join(", ");

const SECURITY_HEADERS: Readonly<Record<string, string>> = Object.freeze({
  "Content-Security-Policy": OPERATOR_CONTENT_SECURITY_POLICY,
  "Permissions-Policy": OPERATOR_PERMISSIONS_POLICY,
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
});

function commaSeparatedValues(value: string | number | string[] | undefined): string[] {
  if (value == null) return [];
  return (Array.isArray(value) ? value : [String(value)])
    .flatMap((part) => part.split(","))
    .map((part) => part.trim())
    .filter(Boolean);
}

export function mergeVaryHeader(
  current: string | number | string[] | undefined,
  additions: string | number | string[] | undefined,
): string {
  const values = [...commaSeparatedValues(current), ...commaSeparatedValues(additions)];
  if (values.includes("*")) return "*";

  const unique = new Map<string, string>();
  for (const value of values) {
    const key = value.toLowerCase();
    if (!unique.has(key)) unique.set(key, value);
  }
  return Array.from(unique.values()).join(", ");
}

export function isPublicBuildAsset(pathname: string): boolean {
  return pathname.startsWith("/_nuxt/") || pathname.startsWith("/_fonts/");
}

export function operatorResponseHeaders(options: {
  pathname: string;
  secure: boolean;
  existingVary?: string | number | string[];
}): Record<string, string> {
  const headers = { ...SECURITY_HEADERS };

  if (options.secure) {
    headers["Strict-Transport-Security"] = `max-age=${ONE_YEAR_SECONDS}; includeSubDomains`;
  }

  if (!isPublicBuildAsset(options.pathname)) {
    headers["Cache-Control"] = "private, no-store, max-age=0";
    headers.Expires = "0";
    headers.Pragma = "no-cache";
    headers.Vary = mergeVaryHeader(options.existingVary, "Cookie");
  }

  return headers;
}

export function requestIsHttps(event: H3Event): boolean {
  const forwardedProtocol = getRequestHeader(event, "x-forwarded-proto")
    ?.split(",", 1)[0]
    ?.trim()
    .toLowerCase();
  if (forwardedProtocol) return forwardedProtocol === "https";
  return getRequestURL(event).protocol === "https:";
}

export function applyOperatorSecurityHeaders(event: H3Event): void {
  const pathname = getRequestURL(event).pathname;
  const headers = operatorResponseHeaders({
    pathname,
    secure: requestIsHttps(event),
    existingVary: getResponseHeader(event, "vary"),
  });
  setResponseHeaders(event, headers);
}

export function applyPrivateNoStore(event: H3Event, upstreamVary?: string | null): void {
  setResponseHeaders(event, {
    "Cache-Control": "private, no-store, max-age=0",
    Expires: "0",
    Pragma: "no-cache",
    Vary: mergeVaryHeader(getResponseHeader(event, "vary"), ["Cookie", upstreamVary || ""]),
  });
}
