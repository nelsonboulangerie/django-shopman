// Proxy BFF canônico das superfícies de operador: repassa a chamada same-origin
// do Nitro para o Django (api.<zona>), cuidando de cookie de sessão, CSRF
// (bootstrap via /admin/login/ quando o token ainda não existe), redirects e
// sanidade de contrato (X-API-Version). Vive na layer operator-kit e chega aos
// apps hospedeiros por auto-import do Nitro (mesmo padrão do eventStream.ts e
// do apiVersion.ts ao lado).
import {
  appendResponseHeader,
  createError,
  getQuery,
  getRequestHeader,
  readRawBody,
  setResponseHeader,
  setResponseStatus,
  splitCookiesString,
  type H3Event,
} from "h3";
import { withQuery } from "ufo";
import { resolveDjangoBaseUrl } from "./djangoBaseUrl";
import {
  applyOperatorSecurityHeaders,
} from "./securityHeaders";
import { applyPrivateNoStore } from "./operatorSecurity";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export const DJANGO_CONDITIONAL_REQUEST_HEADERS = ["if-none-match", "x-request-id"] as const;
export const DJANGO_OPERATIONAL_RESPONSE_HEADERS = [
  "retry-after",
  "idempotency-key",
  "x-correlation-id",
  "etag",
  "x-request-id",
  "x-api-version",
  "x-contract-version",
  "x-resource-version",
  "ratelimit-limit",
  "ratelimit-remaining",
  "ratelimit-reset",
  "x-ratelimit-limit",
  "x-ratelimit-remaining",
  "x-ratelimit-reset",
] as const;

const COOKIE_NAME = /^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/;
const COOKIE_VALUE = /^(?:[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*|"[\x20-\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*")$/;
const COOKIE_DOMAIN = /^\.?[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$/;
const COOKIE_ATTRIBUTE_VALUE = /^[\x20-\x3A\x3C-\x7E]*$/;

export function isSafeDjangoSetCookieHeader(header: string): boolean {
  if (!header || header.length > 4096 || /[\x00-\x1F\x7F]/.test(header)) return false;

  const [pair = "", ...rawAttributes] = header.split(";");
  const separator = pair.indexOf("=");
  if (separator <= 0) return false;
  const name = pair.slice(0, separator).trim();
  const value = pair.slice(separator + 1).trim();
  if (!COOKIE_NAME.test(name) || !COOKIE_VALUE.test(value)) return false;

  let secure = false;
  let path: string | undefined;
  let domain: string | undefined;
  let sameSite: string | undefined;

  for (const rawAttribute of rawAttributes) {
    const attribute = rawAttribute.trim();
    if (!attribute) continue;
    const attributeSeparator = attribute.indexOf("=");
    const attributeName = (attributeSeparator < 0 ? attribute : attribute.slice(0, attributeSeparator)).toLowerCase();
    const attributeValue = attributeSeparator < 0 ? undefined : attribute.slice(attributeSeparator + 1).trim();

    if (["secure", "httponly", "partitioned"].includes(attributeName)) {
      if (attributeValue !== undefined) return false;
      if (attributeName === "secure") secure = true;
      continue;
    }
    if (attributeValue === undefined || !COOKIE_ATTRIBUTE_VALUE.test(attributeValue)) return false;

    if (attributeName === "path") {
      if (!attributeValue.startsWith("/") || attributeValue.includes("\\")) return false;
      path = attributeValue;
    } else if (attributeName === "domain") {
      if (!COOKIE_DOMAIN.test(attributeValue)) return false;
      domain = attributeValue;
    } else if (attributeName === "samesite") {
      if (!/^(?:lax|strict|none)$/i.test(attributeValue)) return false;
      sameSite = attributeValue.toLowerCase();
    } else if (attributeName === "max-age") {
      if (!/^-?\d+$/.test(attributeValue)) return false;
    } else if (attributeName === "expires") {
      if (!/^[A-Za-z]{3}, \d{2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(attributeValue)) return false;
    } else if (attributeName === "priority") {
      if (!/^(?:low|medium|high)$/i.test(attributeValue)) return false;
    } else {
      return false;
    }
  }

  if (sameSite === "none" && !secure) return false;
  if (name.startsWith("__Secure-") && !secure) return false;
  if (name.startsWith("__Host-") && (!secure || domain !== undefined || path !== "/")) return false;
  return true;
}

export function isSafeDjangoLocation(location: string): boolean {
  return location.startsWith("/")
    && !location.startsWith("//")
    && !location.includes("\\")
    && !/[\x00-\x1F\x7F]/.test(location);
}

export function mutationHeaders(read: (name: string) => string | undefined): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const name of ["idempotency-key", "if-match", "x-correlation-id"]) {
    const value = read(name);
    if (value) headers[name] = value;
  }
  return headers;
}

export function csrfTokenFromCookieHeader(cookie: string | undefined): string {
  return cookie
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrftoken="))
    ?.slice("csrftoken=".length) || "";
}

export function mergeSetCookieIntoCookieHeader(cookie: string | undefined, setCookie: string): string {
  if (!isSafeDjangoSetCookieHeader(setCookie)) return cookie || "";
  const [pair = ""] = setCookie.split(";");
  const [name, ...valueParts] = pair.split("=");
  const value = valueParts.join("=");
  if (!name || value == null) return cookie || "";

  const next = new Map<string, string>();
  for (const part of (cookie || "").split(";")) {
    const [cookieName, ...cookieValue] = part.trim().split("=");
    if (cookieName) next.set(cookieName, cookieValue.join("="));
  }
  next.set(name, value);
  return Array.from(next.entries()).map(([cookieName, cookieValue]) => `${cookieName}=${cookieValue}`).join("; ");
}

async function ensureDjangoCsrfCookie(
  event: H3Event,
  djangoBaseUrl: string,
  cookie: string | undefined,
): Promise<{ cookie: string | undefined; token: string }> {
  let token = csrfTokenFromCookieHeader(cookie);
  if (token) return { cookie, token: decodeURIComponent(token) };

  const response = await $fetch.raw(`${djangoBaseUrl}/admin/login/`, {
    method: "GET",
    headers: {
      accept: "text/html",
      ...(cookie ? { cookie } : {}),
    },
    ignoreResponseError: true,
  });

  let mergedCookie = cookie;
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) {
    for (const cookieHeader of splitCookiesString(setCookie)) {
      if (!isSafeDjangoSetCookieHeader(cookieHeader)) continue;
      appendResponseHeader(event, "set-cookie", cookieHeader);
      mergedCookie = mergeSetCookieIntoCookieHeader(mergedCookie, cookieHeader);
    }
  }

  token = csrfTokenFromCookieHeader(mergedCookie);
  return { cookie: mergedCookie, token: token ? decodeURIComponent(token) : "" };
}

/**
 * O caminho tenta ESCAPAR do prefixo em que foi admitido?
 *
 * O catch-all do Nitro entrega `event.context.params.path` CRU e sem
 * normalizar, e o parser de URL do `$fetch` colapsa `..` ao montar o alvo. Sem
 * esta trava, `GET /api/v1/cart/../backstage/pos/cash/movement/` passava pela
 * allowlist (começa com `cart/`) e chegava no backstage — e é o PRÓPRIO BFF que
 * fornece o `X-CSRFToken` e forja `Origin`/`Referer`. Como o cookie de operador
 * é de domínio-pai, um foothold same-site na loja deixava de "incomodar o
 * cliente" e passava a MOVER DINHEIRO no caixa.
 *
 * Decodifica até estabilizar (no máximo 3 voltas) porque `%2e%2e` e
 * `%252e%252e` são o mesmo pedido escrito de outro jeito. Percent-encoding
 * malformado é recusa, não tentativa de adivinhação.
 */
export function hasPathTraversal (path: string): boolean {
  let current = path;
  for (let i = 0; i < 3; i++) {
    if (current.includes("\\")) return true;
    if (current.split("/").some((seg) => seg === "." || seg === "..")) return true;
    let next: string;
    try {
      next = decodeURIComponent(current);
    } catch {
      return true; // encoding malformado: recusa, não adivinha
    }
    if (next === current) return false;
    current = next;
  }
  return true // não estabilizou em 3 voltas: recusa
}

export async function proxyDjangoApi(event: H3Event, path: string) {
  return proxyDjangoPath(event, `/api/v1/${path}`);
}

export async function proxyDjangoPath(event: H3Event, fullPath: string) {
  applyOperatorSecurityHeaders(event);
  if (hasPathTraversal(fullPath)) {
    throw createError({ statusCode: 400, statusMessage: "Bad Request" });
  }
  const config = useRuntimeConfig(event);
  const djangoBaseUrl = resolveDjangoBaseUrl(config.djangoBaseUrl);
  const method = event.method || "GET";
  const isUnsafeMethod = UNSAFE_METHODS.has(method.toUpperCase());
  const normalizedPath = fullPath.endsWith("/") ? fullPath : `${fullPath}/`;
  const target = withQuery(`${djangoBaseUrl}${normalizedPath}`, getQuery(event));
  const djangoOrigin = new URL(djangoBaseUrl).origin;

  const headers: Record<string, string> = {
    accept: getRequestHeader(event, "accept") || "application/json",
    ...mutationHeaders((name) => getRequestHeader(event, name)),
  };

  let cookie = getRequestHeader(event, "cookie");
  if (cookie) headers.cookie = cookie;

  const contentType = getRequestHeader(event, "content-type");
  if (contentType) headers["content-type"] = contentType;

  for (const name of DJANGO_CONDITIONAL_REQUEST_HEADERS) {
    const value = getRequestHeader(event, name);
    if (value) headers[name] = value;
  }

  // Comandos mutantes dependem da mesma key no browser, BFF e Django. Não
  // repassar transformaria um retry de rede em um segundo efeito externo.
  const idempotencyKey = getRequestHeader(event, "idempotency-key");
  if (idempotencyKey) headers["idempotency-key"] = idempotencyKey;

  // O IP do cliente tem de atravessar o BFF, senão TODO visitante anônimo vira
  // um balde de rate limit só. O navegador fala com o Nitro same-origin, e o
  // Nitro abre conexão NOVA para o Django: sem repassar o XFF, o único IP que o
  // Django vê é o de saída deste processo — idêntico para todo mundo. Efeito
  // medido: ~20 chamadas em /auth/request-code/ e ninguém mais entra na loja
  // por uma hora; checkout anônimo em 3/min para a loja INTEIRA.
  //
  // Repassar o valor CRU é seguro porque quem lê conta da DIREITA
  // (`doorman.get_client_ip(trusted_proxy_depth)` e o `NUM_PROXIES` do DRF): o
  // edge da plataforma acrescenta o IP real à direita, então um XFF forjado
  // pelo cliente entra à esquerda e não desloca a contagem.
  const forwardedFor = getRequestHeader(event, "x-forwarded-for");
  if (forwardedFor) headers["x-forwarded-for"] = forwardedFor;

  if (isUnsafeMethod) {
    headers.origin = djangoOrigin;
    headers.referer = `${djangoOrigin}/`;
  }

  const clientCsrfHeader = getRequestHeader(event, "x-csrftoken") || getRequestHeader(event, "x-csrf-token");
  const csrfCookie = csrfTokenFromCookieHeader(cookie);
  if (csrfCookie) headers["x-csrftoken"] = decodeURIComponent(csrfCookie);
  else if (clientCsrfHeader) headers["x-csrftoken"] = clientCsrfHeader;

  if (isUnsafeMethod && !headers["x-csrftoken"]) {
    const csrf = await ensureDjangoCsrfCookie(event, djangoBaseUrl, cookie);
    cookie = csrf.cookie;
    if (cookie) headers.cookie = cookie;
    if (csrf.token) headers["x-csrftoken"] = csrf.token;
  }

  const body = ["GET", "HEAD"].includes(method) ? undefined : await readRawBody(event, false);

  const response = await $fetch.raw(target, {
    method,
    headers,
    body,
    ignoreResponseError: true,
    redirect: "manual",
  });

  // Sanidade de contrato: o Django carimba /api/v1/ com X-API-Version; major
  // divergente vira warning estruturado no Nitro (apiVersion.ts ao lado,
  // auto-importado) — nunca bloqueia a resposta.
  warnOnApiVersionMismatch(response.headers.get("x-api-version"), { path: normalizedPath });

  const setCookie = response.headers.get("set-cookie");
  if (setCookie) {
    for (const cookieHeader of splitCookiesString(setCookie)) {
      if (!isSafeDjangoSetCookieHeader(cookieHeader)) continue;
      appendResponseHeader(event, "set-cookie", cookieHeader);
    }
  }

  const location = response.headers.get("location");
  if (location && isSafeDjangoLocation(location)) setResponseHeader(event, "location", location);

  const responseContentType = response.headers.get("content-type");
  if (responseContentType) setResponseHeader(event, "content-type", responseContentType);

  // Allowlist operacional: o browser precisa saber quando repetir e qual
  // receipt/request citar, sem espelhar headers arbitrários do upstream.
  for (const name of DJANGO_OPERATIONAL_RESPONSE_HEADERS) {
    const value = response.headers.get(name);
    if (value) setResponseHeader(event, name, value);
  }

  // O upstream pode variar também por idioma/encoding; preservamos essa informação,
  // mas nunca aceitamos que uma resposta de operador se torne pública/cacheável.
  applyPrivateNoStore(event, response.headers.get("vary"));

  setResponseStatus(event, response.status);
  return response._data;
}
