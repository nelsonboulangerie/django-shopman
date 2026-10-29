// O BFF distingue "o Django não respondeu" de "o Django respondeu com erro".
// Antes, uma falha de conexão saía como 500 genérico do Nitro e uma chamada sem
// resposta pendurava até o TCP desistir; o PDV não tinha como saber que era o
// caminho, e travava em "resultado incerto".
import { IncomingMessage, ServerResponse } from "node:http";
import { Socket } from "node:net";
import { createEvent, type H3Event } from "h3";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  DJANGO_UPSTREAM_TIMEOUT_MS,
  isEdgeGatewayFailure,
  proxyDjangoPath,
} from "../server/utils/djangoProxy";

const DJANGO = "http://django.internal:8000";

function makeEvent(): { event: H3Event; res: ServerResponse } {
  const request = new IncomingMessage(new Socket());
  request.method = "GET";
  request.url = "/api/v1/backstage/pos/";
  request.headers = {};
  const response = new ServerResponse(request);
  return { event: createEvent(request, response), res: response };
}

function stubRaw(raw: (...args: unknown[]) => Promise<unknown>) {
  const spy = vi.fn(raw);
  vi.stubGlobal("$fetch", Object.assign(vi.fn(), { raw: spy }));
  return spy;
}

describe("proxyDjangoPath — upstream inalcançável", () => {
  beforeEach(() => {
    vi.stubGlobal("useRuntimeConfig", () => ({ djangoBaseUrl: DJANGO }));
    vi.stubGlobal("warnOnApiVersionMismatch", vi.fn());
  });

  it("conexão recusada vira 502 com código próprio, não 500 genérico", async () => {
    stubRaw(() => Promise.reject(Object.assign(new TypeError("fetch failed"), { cause: { code: "ECONNREFUSED" } })));
    const { event, res } = makeEvent();

    const data = await proxyDjangoPath(event, "/api/v1/backstage/pos");

    expect(res.statusCode).toBe(502);
    expect(data).toMatchObject({ detail: expect.any(String), error: { code: "upstream_unreachable" } });
    expect(res.getHeader("cache-control")).toBe("private, no-store, max-age=0");
  });

  it("tempo esgotado vira 504 upstream_timeout (o pedido pode ter chegado)", async () => {
    stubRaw(() => Promise.reject(new DOMException("The operation was aborted due to timeout", "TimeoutError")));
    const { event, res } = makeEvent();

    const data = await proxyDjangoPath(event, "/api/v1/backstage/pos");

    expect(res.statusCode).toBe(504);
    expect(data).toMatchObject({ error: { code: "upstream_timeout" } });
  });

  it("toda chamada ao Django leva um prazo (AbortSignal)", async () => {
    const raw = stubRaw(() => Promise.resolve({ status: 200, _data: {}, headers: new Headers({ "x-api-version": "1" }) }));
    const timeout = vi.spyOn(AbortSignal, "timeout");
    const { event } = makeEvent();

    await proxyDjangoPath(event, "/api/v1/backstage/pos");

    expect(timeout).toHaveBeenCalledWith(DJANGO_UPSTREAM_TIMEOUT_MS);
    expect((raw.mock.calls[0]![1] as { signal?: AbortSignal }).signal).toBeInstanceOf(AbortSignal);
    timeout.mockRestore();
  });

  it("502/503 da borda (HTML, sem X-API-Version) vira 503 upstream_unavailable", async () => {
    stubRaw(() => Promise.resolve({
      status: 502,
      _data: "<html>Bad gateway</html>",
      headers: new Headers({ "content-type": "text/html" }),
    }));
    const { event, res } = makeEvent();

    const data = await proxyDjangoPath(event, "/api/v1/backstage/pos");

    expect(res.statusCode).toBe(503);
    expect(data).toMatchObject({ error: { code: "upstream_unavailable" } });
  });

  it("o 503 do PRÓPRIO Django passa como veio: ele respondeu", async () => {
    stubRaw(() => Promise.resolve({
      status: 503,
      _data: { detail: "Manutenção." },
      headers: new Headers({ "content-type": "application/json", "x-api-version": "1" }),
    }));
    const { event, res } = makeEvent();

    const data = await proxyDjangoPath(event, "/api/v1/backstage/pos");

    expect(res.statusCode).toBe(503);
    expect(data).toEqual({ detail: "Manutenção." });
  });

  it("isEdgeGatewayFailure só pega 502/503/504 que não vieram do Django", () => {
    expect(isEdgeGatewayFailure(500, new Headers())).toBe(false);
    expect(isEdgeGatewayFailure(502, new Headers({ "content-type": "text/html" }))).toBe(true);
    expect(isEdgeGatewayFailure(502, new Headers({ "x-api-version": "1" }))).toBe(false);
    expect(isEdgeGatewayFailure(504, new Headers({ "content-type": "application/json" }))).toBe(false);
  });
});
