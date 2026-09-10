// Proxy BFF canônico das superfícies de operador (server/utils/djangoProxy.ts).
// Exercita as decisões de transporte de CSRF/cookie — preservar a sessão ao
// atualizar o csrftoken, valores com "=" (assinados/base64) intactos — e trava
// por fonte as decisões de segurança/contrato: origin normalizado para o do
// Django e checagem de X-API-Version fiada dentro do proxy (PR #71). Espelha a
// suíte do storefront (djangoProxy.test.ts), que mantém proxy próprio.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { csrfTokenFromCookieHeader, mergeSetCookieIntoCookieHeader } from "../server/utils/djangoProxy";
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

  it("normaliza origin/referer de método inseguro para o origin do Django", () => {
    expect(proxySource).toContain("headers.origin = djangoOrigin");
    expect(proxySource).toContain("headers.referer = `${djangoOrigin}/`");
    expect(proxySource).not.toContain('getRequestHeader(event, "origin")');
    expect(proxySource).not.toContain('getRequestHeader(event, "referer")');
  });

  it("mantém a checagem de X-API-Version fiada dentro do proxy", () => {
    expect(proxySource).toContain('warnOnApiVersionMismatch(response.headers.get("x-api-version")');
    expect(proxySource).toContain('appendResponseHeader(event, "x-api-version"');
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
