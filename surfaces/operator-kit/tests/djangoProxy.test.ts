// Proxy BFF canônico das superfícies de operador (server/utils/djangoProxy.ts).
// Exercita as decisões de transporte de CSRF/cookie — preservar a sessão ao
// atualizar o csrftoken, valores com "=" (assinados/base64) intactos — e trava
// por fonte as decisões de segurança/contrato: origin normalizado para o do
// Django e checagem de X-API-Version fiada dentro do proxy (PR #71). Espelha a
// suíte do storefront (djangoProxy.test.ts), que mantém proxy próprio.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  csrfTokenFromCookieHeader,
  DJANGO_CONDITIONAL_REQUEST_HEADERS,
  DJANGO_OPERATIONAL_RESPONSE_HEADERS,
  isSafeDjangoLocation,
  isSafeDjangoSetCookieHeader,
  mergeSetCookieIntoCookieHeader,
  mutationHeaders,
} from "../server/utils/djangoProxy";

import {
  assertProductionDjangoConfiguration,
  configuredDjangoBaseUrl,
  isExplicitTestRuntime,
  isProductionRuntime,
  resolveDjangoBaseUrl,
} from "../server/utils/djangoBaseUrl";

const proxySource = readFileSync(fileURLToPath(new URL("../server/utils/djangoProxy.ts", import.meta.url)), "utf8");

describe("Django proxy — transporte de CSRF/cookie do BFF de operador", () => {
  it("preserva o cookie de sessão do Django ao atualizar o estado de CSRF", () => {
    const cookie = "sessionid=session-123; csrftoken=old-token";
    expect(csrfTokenFromCookieHeader(cookie)).toBe("old-token");
    expect(mergeSetCookieIntoCookieHeader(cookie, "csrftoken=new-token; Path=/; SameSite=Lax")).toBe(
      "sessionid=session-123; csrftoken=new-token",
    );
    expect(mergeSetCookieIntoCookieHeader(cookie, "other=value=with-equals; Path=/")).toBe(
      "sessionid=session-123; csrftoken=old-token; other=value=with-equals",
    );
  });

  it('mantém valores de cookie com "=" intactos (assinados/base64)', () => {
    const cookie = "csrftoken=old-token";
    expect(mergeSetCookieIntoCookieHeader(cookie, "sessionid=abc.def=ghi==; Path=/; HttpOnly")).toBe(
      "csrftoken=old-token; sessionid=abc.def=ghi==",
    );
  });

  it("aceita cookies Django válidos e recusa atributos, prefixos ou bytes inseguros", () => {
    expect(isSafeDjangoSetCookieHeader(
      "sessionid=abc.def=ghi==; expires=Wed, 09 Sep 2026 20:00:00 GMT; Max-Age=31449600; Path=/; Secure; HttpOnly; SameSite=Lax",
    )).toBe(true);
    expect(isSafeDjangoSetCookieHeader("__Host-sessionid=s1; Path=/; Secure; HttpOnly; SameSite=Strict")).toBe(true);
    expect(isSafeDjangoSetCookieHeader("__Host-sessionid=s1; Path=/; HttpOnly")).toBe(false);
    expect(isSafeDjangoSetCookieHeader("sessionid=s1; Path=/; Surprise=enabled")).toBe(false);
    expect(isSafeDjangoSetCookieHeader("sessionid=s1\r\nX-Injected: yes; Path=/")).toBe(false);
  });

  it("repassa somente redirects same-origin por caminho absoluto", () => {
    expect(isSafeDjangoLocation("/admin/login/?next=%2Fcampaigns%2F")).toBe(true);
    expect(isSafeDjangoLocation("https://evil.example/steal")).toBe(false);
    expect(isSafeDjangoLocation("//evil.example/steal")).toBe(false);
    expect(isSafeDjangoLocation("/\\evil.example/steal")).toBe(false);
    expect(isSafeDjangoLocation("/ok\r\nX-Injected: yes")).toBe(false);
  });

  it("normaliza origin/referer de método inseguro para o origin do Django", () => {
    expect(proxySource).toContain("headers.origin = djangoOrigin");
    expect(proxySource).toContain("headers.referer = `${djangoOrigin}/`");
    expect(proxySource).toContain('getRequestHeader(event, "idempotency-key")');
    expect(proxySource).not.toContain('getRequestHeader(event, "origin")');
    expect(proxySource).not.toContain('getRequestHeader(event, "referer")');
  });

  it("preserva por allowlist a revalidação e os metadados operacionais", () => {
    expect(DJANGO_CONDITIONAL_REQUEST_HEADERS).toEqual(["if-none-match", "x-request-id"]);
    expect(DJANGO_OPERATIONAL_RESPONSE_HEADERS).toEqual(expect.arrayContaining([
      "retry-after",
      "etag",
      "x-request-id",
      "x-api-version",
      "x-contract-version",
      "x-resource-version",
      "ratelimit-limit",
      "ratelimit-remaining",
      "ratelimit-reset",
    ]));
    expect(DJANGO_OPERATIONAL_RESPONSE_HEADERS).not.toContain("cache-control");
    expect(proxySource).toContain("for (const name of DJANGO_CONDITIONAL_REQUEST_HEADERS)");
    expect(proxySource).toContain("for (const name of DJANGO_OPERATIONAL_RESPONSE_HEADERS)");
  });

  it("mantém a checagem de X-API-Version fiada dentro do proxy", () => {
    expect(proxySource).toContain('warnOnApiVersionMismatch(response.headers.get("x-api-version")');
    expect(DJANGO_OPERATIONAL_RESPONSE_HEADERS).toContain("x-api-version");
    expect(proxySource).toContain('applyPrivateNoStore(event, response.headers.get("vary"))');
  });

  it("recusa upstream ausente, local ou HTTP remoto em production", () => {
    for (const value of [undefined, "http://127.0.0.1:8000/", "http://api.example.test/"]) {
      expect(() => resolveDjangoBaseUrl(value, { production: true })).toThrow();
    }
    expect(resolveDjangoBaseUrl("https://api.example.test/", { production: true })).toBe(
      "https://api.example.test",
    );
  });

  it("faz fail-fast pela configuração real de build e só libera localhost em dev/test explícito", () => {
    expect(isProductionRuntime({ NODE_ENV: "production", SHOPMAN_ENVIRONMENT: "staging" })).toBe(true);
    expect(isExplicitTestRuntime({ NODE_ENV: "production", SHOPMAN_ENVIRONMENT: "test" })).toBe(false);
    expect(isExplicitTestRuntime({
      NODE_ENV: "production",
      SHOPMAN_ENVIRONMENT: "test",
      SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM: "1",
    })).toBe(true);
    expect(() => configuredDjangoBaseUrl({ NODE_ENV: "production" })).toThrow();
    expect(() =>
      configuredDjangoBaseUrl({
        NODE_ENV: "production",
        SHOPMAN_ENVIRONMENT: "staging",
        NUXT_DJANGO_BASE_URL: "http://api.example.test",
      }),
    ).toThrow();
    expect(() =>
      configuredDjangoBaseUrl({
        NODE_ENV: "production",
        SHOPMAN_ENVIRONMENT: "development",
        NUXT_DJANGO_BASE_URL: "https://api.example.test",
      }),
    ).toThrow();
    expect(
      assertProductionDjangoConfiguration({
        SHOPMAN_ENVIRONMENT: "production",
        NUXT_DJANGO_BASE_URL: "https://api.example.test/",
      }),
    ).toBe("https://api.example.test");
    expect(
      configuredDjangoBaseUrl({
        NODE_ENV: "production",
        SHOPMAN_ENVIRONMENT: "test",
        SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM: "1",
      }),
    ).toBe("http://127.0.0.1:8000");
    expect(() => configuredDjangoBaseUrl({ NODE_ENV: "production", SHOPMAN_ENVIRONMENT: "test" })).toThrow();
    expect(configuredDjangoBaseUrl({ NODE_ENV: "development" })).toBe("http://127.0.0.1:8000");
  });
});


describe("BFF — intenção e precondição", () => {
  it("preserva somente os headers autorizados da intenção, sem aceitar identidade do cliente", () => {
    const input: Record<string, string> = {
      "idempotency-key": "same-intention",
      "if-match": '"revision-1"',
      "x-correlation-id": "trace-1",
      "x-operator-id": "other-user",
      authorization: "Bearer forged",
    };
    expect(mutationHeaders((name) => input[name])).toEqual({
      "idempotency-key": "same-intention",
      "if-match": '"revision-1"',
      "x-correlation-id": "trace-1",
    });
    expect(mutationHeaders(() => undefined)).toEqual({});
  });
});
