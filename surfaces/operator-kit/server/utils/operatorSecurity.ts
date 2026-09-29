import {
  getRequestHeader,
  getRequestURL,
  getResponseHeader,
  setResponseHeaders,
  type H3Event,
} from "h3";

const ONE_YEAR_SECONDS = 31_536_000;

const OPERATOR_CSP_DIRECTIVES: ReadonlyArray<readonly [string, string]> = [
  ["default-src", "'self'"],
  ["base-uri", "'self'"],
  ["connect-src", "'self'"],
  ["font-src", "'self' data:"],
  ["form-action", "'self'"],
  ["frame-ancestors", "'none'"],
  ["frame-src", "'none'"],
  ["img-src", "'self' data: blob:"],
  ["manifest-src", "'self'"],
  ["media-src", "'self' blob:"],
  ["object-src", "'none'"],
  // Nuxt serializa o payload de hidratação em script inline. Nonces devem
  // substituir unsafe-inline num WP de CSP dinâmica; eval e origens externas
  // permanecem fechados desde já.
  ["script-src", "'self' 'unsafe-inline'"],
  ["style-src", "'self' 'unsafe-inline'"],
  ["worker-src", "'self' blob:"],
];

export const OPERATOR_CONTENT_SECURITY_POLICY = OPERATOR_CSP_DIRECTIVES.map(
  ([directive, sources]) => `${directive} ${sources}`,
).join("; ");

// Exceção de CSP é por app e por diretiva (SEC-SURF-001, item 5): o app declara
// em `runtimeConfig.operatorCspAllow` só a origem que uma função real exige.
// Diretivas de execução e de enquadramento nunca abrem, e fontes que desligam a
// política (`*`, `'unsafe-*'`, esquemas genéricos além de `https:`) são recusadas.
export const OPERATOR_CSP_EXTENSIBLE_DIRECTIVES = Object.freeze([
  "connect-src",
  "font-src",
  "img-src",
  "media-src",
] as const);

export type OperatorCspDirective = (typeof OPERATOR_CSP_EXTENSIBLE_DIRECTIVES)[number];
export type OperatorCspAllow = Partial<Record<OperatorCspDirective, readonly string[]>>;

const ALLOWED_SOURCE = /^(https:|https:\/\/[a-z0-9.-]+(:\d+)?|http:\/\/(127\.0\.0\.1|localhost)(:(\d+|\*))?)$/i;

export function operatorBaselineContentSecurityPolicy(allow?: OperatorCspAllow | null): string {
  if (!allow || Object.keys(allow).length === 0) return OPERATOR_CONTENT_SECURITY_POLICY;
  for (const [directive, sources] of Object.entries(allow)) {
    if (!(OPERATOR_CSP_EXTENSIBLE_DIRECTIVES as readonly string[]).includes(directive)) {
      throw new Error(`CSP: a diretiva ${directive} não aceita exceção por app.`);
    }
    for (const source of sources ?? []) {
      if (!ALLOWED_SOURCE.test(source)) {
        throw new Error(`CSP: a origem ${source} não é aceita em ${directive}.`);
      }
    }
  }
  return OPERATOR_CSP_DIRECTIVES.map(([directive, sources]) => {
    const extra = allow[directive as OperatorCspDirective] ?? [];
    const merged = [...sources.split(" "), ...extra.filter((source) => !sources.split(" ").includes(source))];
    return `${directive} ${merged.join(" ")}`;
  }).join("; ");
}

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
  cspAllow?: OperatorCspAllow | null;
}): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Security-Policy": operatorBaselineContentSecurityPolicy(options.cspAllow),
    ...SECURITY_HEADERS,
  };

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

export function applyOperatorBaselineSecurityHeaders(
  event: H3Event,
  cspAllow?: OperatorCspAllow | null,
): void {
  const pathname = getRequestURL(event).pathname;
  const headers = operatorResponseHeaders({
    pathname,
    secure: requestIsHttps(event),
    existingVary: getResponseHeader(event, "vary"),
    cspAllow,
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
