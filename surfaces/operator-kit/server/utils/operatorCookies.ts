// A sessao direta do Admin e a sessao compartilhada pelos apps de operador
// vivem no mesmo registrable domain, mas nao podem ser o mesmo cookie. Um
// lock/PIN do PDV deve afetar gestor/KDS/etc., nunca a aba do Admin.

import { DEVICE_ACTIVITY_COOKIE_NAME } from "../../app/utils/deviceActivity";

export const DJANGO_SESSION_COOKIE_NAME = "sessionid";
export const DJANGO_CSRF_COOKIE_NAME = "csrftoken";
export const OPERATOR_SESSION_COOKIE_NAME = "shopman_operator_sessionid";
export const OPERATOR_CSRF_COOKIE_NAME = "shopman_operator_csrftoken";

const COOKIE_NAME = /^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/;
const COOKIE_VALUE = /^(?:[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*|"[\x20-\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*")$/;
const COOKIE_DOMAIN = /^\.?[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$/;
const COOKIE_ATTRIBUTE_VALUE = /^[\x20-\x3A\x3C-\x7E]*$/;

export function isSafeDjangoSetCookieHeader(header: string): boolean {
  // Casar caractere de controle É o ponto: um Set-Cookie com CR/LF/NUL injeta cabeçalho
  // na resposta que o BFF devolve ao operador. A regra supõe engano; aqui é a defesa.
  // eslint-disable-next-line no-control-regex
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

type CookiePair = { name: string; value: string };

function cookiePairs(header: string | undefined): CookiePair[] {
  const pairs: CookiePair[] = [];
  for (const rawPair of (header || "").split(";")) {
    const separator = rawPair.indexOf("=");
    if (separator <= 0) continue;
    const name = rawPair.slice(0, separator).trim();
    const value = rawPair.slice(separator + 1).trim();
    if (COOKIE_NAME.test(name) && COOKIE_VALUE.test(value)) pairs.push({ name, value });
  }
  return pairs;
}

/**
 * Constroi o Cookie enviado ao Django pelas surfaces de operador.
 *
 * `sessionid`/`csrftoken` crus pertencem ao Admin e morrem nesta fronteira. Os
 * cookies namespaced, compartilhados em `.boulangerie.com.br`, viram os nomes
 * que o Django conhece somente na conexao interna BFF -> Django. Cookies de
 * confianca da estacao e os demais pares continuam intactos. O relogio de
 * atividade do aparelho (`app/utils/deviceActivity.ts`) e assunto do navegador
 * — a trava do PDV — e tambem morre aqui: o Django nao tem o que fazer com ele.
 */
export function operatorCookieHeaderForDjango(browserCookie: string | undefined): string {
  let operatorSession: string | undefined;
  let operatorCsrf: string | undefined;
  const passthrough: CookiePair[] = [];

  for (const pair of cookiePairs(browserCookie)) {
    if (pair.name === OPERATOR_SESSION_COOKIE_NAME) {
      operatorSession = pair.value;
    } else if (pair.name === OPERATOR_CSRF_COOKIE_NAME) {
      operatorCsrf = pair.value;
    } else if (
      pair.name !== DJANGO_SESSION_COOKIE_NAME
      && pair.name !== DJANGO_CSRF_COOKIE_NAME
      && pair.name !== DEVICE_ACTIVITY_COOKIE_NAME
    ) {
      passthrough.push(pair);
    }
  }

  if (operatorSession !== undefined) {
    passthrough.push({ name: DJANGO_SESSION_COOKIE_NAME, value: operatorSession });
  }
  if (operatorCsrf !== undefined) {
    passthrough.push({ name: DJANGO_CSRF_COOKIE_NAME, value: operatorCsrf });
  }
  return passthrough.map(({ name, value }) => `${name}=${value}`).join("; ");
}

/**
 * Traduz Set-Cookie do Django para o pote exclusivo dos apps de operador.
 * Preserva Domain/Path/Secure/HttpOnly/SameSite e tambem a expiracao vazia que
 * `logout()` emite, portanto login e logout continuam SSO entre as surfaces.
 */
export function operatorSetCookieHeaderForBrowser(djangoHeader: string): string | null {
  if (!isSafeDjangoSetCookieHeader(djangoHeader)) return null;
  const separator = djangoHeader.indexOf("=");
  const name = djangoHeader.slice(0, separator).trim();
  const mappedName = name === DJANGO_SESSION_COOKIE_NAME
    ? OPERATOR_SESSION_COOKIE_NAME
    : name === DJANGO_CSRF_COOKIE_NAME
      ? OPERATOR_CSRF_COOKIE_NAME
      : name;
  return `${mappedName}${djangoHeader.slice(separator)}`;
}
