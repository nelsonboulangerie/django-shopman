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
// Diretivas de enquadramento, de formulário e de base nunca abrem, e fontes que
// desligam a política (`*`, `'unsafe-*'`, esquemas genéricos além de `https:`)
// são recusadas. `script-src` abre mais estreito que as outras: só host `https://`
// explícito ou curinga de subdomínio de um domínio fixo, nunca `https:` nem loopback.
export const OPERATOR_CSP_EXTENSIBLE_DIRECTIVES = Object.freeze([
  "connect-src",
  "font-src",
  "img-src",
  "media-src",
  "script-src",
] as const);

export type OperatorCspDirective = (typeof OPERATOR_CSP_EXTENSIBLE_DIRECTIVES)[number];
export type OperatorCspAllow = Partial<Record<OperatorCspDirective, readonly string[]>>;

const PORT = String.raw`(:\d+)?`;
const EXPLICIT_HTTPS_HOST = String.raw`https:\/\/[a-z0-9-]+(\.[a-z0-9-]+)*` + PORT;
// Curinga só de subdomínio e só sobre um domínio com dois rótulos ou mais:
// `https://*.googleapis.com` passa; `https://*`, `https://*.com` e `https://*.*.com` não.
const SUBDOMAIN_WILDCARD = String.raw`https:\/\/\*\.([a-z0-9-]+(\.[a-z0-9-]+)+)` + PORT;
const LOOPBACK = String.raw`http:\/\/(127\.0\.0\.1|localhost)(:(\d+|\*))?`;

const SOURCE_PATTERN = new RegExp(`^(https:|${EXPLICIT_HTTPS_HOST}|${SUBDOMAIN_WILDCARD}|${LOOPBACK})$`, "i");
const SCRIPT_SOURCE_PATTERN = new RegExp(
  String.raw`^(https:\/\/[a-z0-9-]+(\.[a-z0-9-]+)+` + PORT + `|${SUBDOMAIN_WILDCARD})$`,
  "i",
);
const WILDCARD_BASE = new RegExp(`^${SUBDOMAIN_WILDCARD}$`, "i");

// Segundo nível de sufixo público de país (`com.br`, `co.uk`): o curinga sobre ele
// abriria o domínio de qualquer um, então não conta como domínio fixo.
const PUBLIC_SECOND_LEVEL = new Set(["ac", "co", "com", "edu", "gob", "gov", "mil", "net", "org"]);

function wildcardOverPublicSuffix(source: string): boolean {
  const match = WILDCARD_BASE.exec(source);
  if (!match?.[1]) return false;
  const labels = match[1].toLowerCase().split(".");
  const [first, tld] = labels;
  return labels.length === 2 && tld !== undefined && tld.length === 2 && PUBLIC_SECOND_LEVEL.has(first ?? "");
}

function operatorCspSourceAccepted(directive: OperatorCspDirective, source: string): boolean {
  const pattern = directive === "script-src" ? SCRIPT_SOURCE_PATTERN : SOURCE_PATTERN;
  return pattern.test(source) && !wildcardOverPublicSuffix(source);
}

export function operatorBaselineContentSecurityPolicy(allow?: OperatorCspAllow | null): string {
  if (!allow || Object.keys(allow).length === 0) return OPERATOR_CONTENT_SECURITY_POLICY;
  for (const [directive, sources] of Object.entries(allow)) {
    if (!(OPERATOR_CSP_EXTENSIBLE_DIRECTIVES as readonly string[]).includes(directive)) {
      throw new Error(`CSP: a diretiva ${directive} não aceita exceção por app.`);
    }
    for (const source of sources ?? []) {
      if (!operatorCspSourceAccepted(directive as OperatorCspDirective, source)) {
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

const OPERATOR_PERMISSIONS_DIRECTIVES: ReadonlyArray<readonly [string, string]> = [
  ["browsing-topics", "()"],
  ["camera", "()"],
  ["geolocation", "()"],
  ["microphone", "()"],
  ["payment", "()"],
  ["screen-wake-lock", "(self)"],
  ["usb", "()"],
];

export const OPERATOR_PERMISSIONS_POLICY = OPERATOR_PERMISSIONS_DIRECTIVES.map(
  ([feature, allowlist]) => `${feature}=${allowlist}`,
).join(", ");

// Exceção de Permissions-Policy também é por app e por recurso: o app declara em
// `runtimeConfig.operatorPermissionsAllow` (ex.: `{ camera: "self" }`) só o recurso
// que uma função real usa. Só recursos da lista de base, e só para a própria origem:
// `*` ou outra origem levantam erro. Sem a chave, o header é o de base.
export type OperatorPermissionsFeature =
  | "browsing-topics"
  | "camera"
  | "geolocation"
  | "microphone"
  | "payment"
  | "screen-wake-lock"
  | "usb";
export type OperatorPermissionsAllow = Partial<Record<OperatorPermissionsFeature, "self">>;

export function operatorBaselinePermissionsPolicy(allow?: OperatorPermissionsAllow | null): string {
  if (!allow || Object.keys(allow).length === 0) return OPERATOR_PERMISSIONS_POLICY;
  const known = OPERATOR_PERMISSIONS_DIRECTIVES.map(([feature]) => feature);
  for (const [feature, value] of Object.entries(allow)) {
    if (!known.includes(feature)) {
      throw new Error(`Permissions-Policy: o recurso ${feature} não aceita exceção por app.`);
    }
    if (value !== "self") {
      throw new Error(`Permissions-Policy: ${feature} só abre para a própria origem ("self").`);
    }
  }
  return OPERATOR_PERMISSIONS_DIRECTIVES.map(([feature, allowlist]) =>
    allow[feature as OperatorPermissionsFeature] === "self" ? `${feature}=(self)` : `${feature}=${allowlist}`,
  ).join(", ");
}

const SECURITY_HEADERS: Readonly<Record<string, string>> = Object.freeze({
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
  permissionsAllow?: OperatorPermissionsAllow | null;
}): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Security-Policy": operatorBaselineContentSecurityPolicy(options.cspAllow),
    "Permissions-Policy": operatorBaselinePermissionsPolicy(options.permissionsAllow),
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
  permissionsAllow?: OperatorPermissionsAllow | null,
): void {
  const pathname = getRequestURL(event).pathname;
  const headers = operatorResponseHeaders({
    pathname,
    secure: requestIsHttps(event),
    existingVary: getResponseHeader(event, "vary"),
    cspAllow,
    permissionsAllow,
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
