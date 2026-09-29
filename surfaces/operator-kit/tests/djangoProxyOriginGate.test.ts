import { afterEach, describe, expect, it, vi } from "vitest";
import { createApp, eventHandler, toWebHandler } from "h3";
import { proxyDjangoPath } from "../server/utils/djangoProxy";

// O BFF forja Origin/Referer e monta o X-CSRFToken do próprio cookie, então o
// CSRF do Django sempre passa: a origem tem de ser conferida no BFF. Mesma
// semântica do BFF da loja (storefront-nuxt/tests/djangoProxyTransport.test.ts).

const upstream = vi.fn();
afterEach(() => vi.unstubAllGlobals());

async function request(
  headers: Record<string, string> = {},
  { method = "POST", url = "http://pdv.test/api/v1/backstage/pos/sale/" } = {},
) {
  vi.stubGlobal("useRuntimeConfig", () => ({ djangoBaseUrl: "http://django.test" }));
  vi.stubGlobal("warnOnApiVersionMismatch", vi.fn());
  upstream.mockReset().mockResolvedValue({
    status: 200,
    _data: { ok: true },
    headers: new Headers({ "content-type": "application/json", "x-api-version": "1" }),
  });
  vi.stubGlobal("$fetch", Object.assign(vi.fn(), { raw: upstream }));
  const app = createApp().use(eventHandler((event) => proxyDjangoPath(event, "/api/v1/backstage/pos/sale/")));
  return toWebHandler(app)(new Request(url, {
    method,
    body: method === "GET" ? undefined : JSON.stringify({ sku: "PAO" }),
    headers: { host: new URL(url).host, "content-type": "application/json", cookie: "shopman_operator_csrftoken=synthetic", ...headers },
  }));
}

describe("proxyDjangoPath — origem da mutação", () => {
  it("deixa passar o POST da página do próprio app e forja a origem só depois", async () => {
    const response = await request({ origin: "http://pdv.test", "sec-fetch-site": "same-origin" });
    expect(response.status).toBe(200);
    expect(upstream).toHaveBeenCalledTimes(1);
    expect(upstream.mock.calls[0]?.[1].headers).toMatchObject({
      origin: "http://django.test",
      referer: "http://django.test/",
      "x-csrftoken": "synthetic",
    });
  });

  it("confere contra a origem pública atrás do proxy TLS (X-Forwarded-Proto)", async () => {
    const response = await request({ origin: "https://pdv.test", "x-forwarded-proto": "https" });
    expect(response.status).toBe(200);
    expect(upstream).toHaveBeenCalledTimes(1);
  });

  it.each(["http://evil.test", "http://central.pdv.test", "http://gestor.test", "null"])(
    "recusa POST com Origin %s antes de tocar o Django",
    async (origin) => {
      const response = await request({ origin });
      expect(response.status).toBe(403);
      expect(upstream).not.toHaveBeenCalled();
    },
  );

  it.each(["same-site", "cross-site"])(
    "recusa Sec-Fetch-Site %s mesmo sem Origin (subdomínio irmão)",
    async (site) => {
      const response = await request({ "sec-fetch-site": site });
      expect(response.status).toBe(403);
      expect(upstream).not.toHaveBeenCalled();
    },
  );

  it.each(["PUT", "PATCH", "DELETE"])("vale para %s também", async (method) => {
    const response = await request({ origin: "http://evil.test" }, { method });
    expect(response.status).toBe(403);
    expect(upstream).not.toHaveBeenCalled();
  });

  it("deixa passar pedido sem Origin nem Sec-Fetch-Site (curl, servidor)", async () => {
    const response = await request();
    expect(response.status).toBe(200);
    expect(upstream).toHaveBeenCalledTimes(1);
  });

  it("não mexe em GET: navegação vinda de outro app segue", async () => {
    const response = await request({ "sec-fetch-site": "same-site", origin: "http://central.test" }, { method: "GET" });
    expect(response.status).toBe(200);
    expect(upstream).toHaveBeenCalledTimes(1);
  });
});
