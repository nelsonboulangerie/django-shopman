import { IncomingMessage, ServerResponse } from "node:http";
import { Socket } from "node:net";
import { createEvent, type H3Event } from "h3";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { proxyDjangoPath } from "../server/utils/djangoProxy";

interface RawCall {
  url: string;
  options: {
    method: string;
    headers: Record<string, string>;
    body: unknown;
  };
}

const DJANGO = "http://django.internal:8000";

function makeEvent(headers: Record<string, string>): { event: H3Event; res: ServerResponse } {
  const request = new IncomingMessage(new Socket());
  request.method = "GET";
  request.url = "/api/v1/backstage/marketing/v2/";
  request.headers = headers;
  const response = new ServerResponse(request);
  return { event: createEvent(request, response), res: response };
}

function upstream(status: number, data: unknown, headers: Record<string, string>) {
  return { status, _data: data, headers: new Headers(headers) };
}

describe("proxyDjangoPath — conditional Marketing metadata", () => {
  let calls: RawCall[];

  beforeEach(() => {
    calls = [];
    vi.stubGlobal("useRuntimeConfig", () => ({ djangoBaseUrl: DJANGO }));
    vi.stubGlobal("warnOnApiVersionMismatch", vi.fn());
  });

  it("preserves 304 and only the allowlisted request/response headers", async () => {
    const raw = vi.fn((url: string, options: RawCall["options"]) => {
      calls.push({ url, options });
      return Promise.resolve(upstream(304, undefined, {
        "cache-control": "private, no-cache, must-revalidate",
        etag: 'W/"marketing-v2-known"',
        "retry-after": "11",
        "x-api-version": "1",
        "x-contract-version": "marketing.v2",
        "x-request-id": "req_browser_42",
        "x-resource-version": "18",
        "ratelimit-remaining": "4",
        "x-internal-secret": "must-not-pass",
      }));
    });
    vi.stubGlobal("$fetch", Object.assign(vi.fn(), { raw }));
    const { event, res } = makeEvent({
      "if-none-match": 'W/"marketing-v2-known"',
      "x-request-id": "req_browser_42",
      "x-internal-secret": "must-not-pass",
    });

    const data = await proxyDjangoPath(event, "/api/v1/backstage/marketing/v2");

    expect(calls).toHaveLength(1);
    expect(calls[0]?.options.headers).toMatchObject({
      "if-none-match": 'W/"marketing-v2-known"',
      "x-request-id": "req_browser_42",
    });
    expect(calls[0]?.options.headers["x-internal-secret"]).toBeUndefined();
    expect(res.statusCode).toBe(304);
    expect(data).toBeUndefined();
    expect(res.getHeader("etag")).toBe('W/"marketing-v2-known"');
    expect(res.getHeader("x-contract-version")).toBe("marketing.v2");
    expect(res.getHeader("x-resource-version")).toBe("18");
    expect(res.getHeader("retry-after")).toBe("11");
    expect(res.getHeader("ratelimit-remaining")).toBe("4");
    expect(res.getHeader("x-internal-secret")).toBeUndefined();
    expect(res.getHeader("cache-control")).toBe("private, no-store, max-age=0");
    expect(res.getHeader("content-security-policy")).toContain("frame-ancestors 'none'");
    expect(res.getHeader("x-frame-options")).toBe("DENY");
    expect(res.getHeader("x-powered-by")).toBeUndefined();
  });

  it("preserva cookie e redirect seguros sem aceitar variantes injetáveis ou externas", async () => {
    const raw = vi
      .fn()
      .mockResolvedValueOnce(upstream(302, "", {
        location: "/admin/login/?next=%2Fcampaigns%2F",
        "set-cookie": "sessionid=abc.def=ghi==; Path=/; Secure; HttpOnly; SameSite=Lax",
      }))
      .mockResolvedValueOnce(upstream(302, "", {
        location: "//evil.example/steal",
        "set-cookie": "sessionid=stolen; Path=/; Surprise=enabled",
      }));
    vi.stubGlobal("$fetch", Object.assign(vi.fn(), { raw }));

    const safe = makeEvent({});
    await proxyDjangoPath(safe.event, "/api/v1/backstage/marketing/v2");
    expect(safe.res.getHeader("location")).toBe("/admin/login/?next=%2Fcampaigns%2F");
    expect(safe.res.getHeader("set-cookie")).toBe(
      "shopman_operator_sessionid=abc.def=ghi==; Path=/; Secure; HttpOnly; SameSite=Lax",
    );

    const unsafe = makeEvent({});
    await proxyDjangoPath(unsafe.event, "/api/v1/backstage/marketing/v2");
    expect(unsafe.res.getHeader("location")).toBeUndefined();
    expect(unsafe.res.getHeader("set-cookie")).toBeUndefined();
  });

  it("envia somente a sessão de operador ao Django e mantém cookies de estação", async () => {
    const raw = vi.fn((url: string, options: RawCall["options"]) => {
      calls.push({ url, options });
      return Promise.resolve(upstream(200, {}, {}));
    });
    vi.stubGlobal("$fetch", Object.assign(vi.fn(), { raw }));
    const { event } = makeEvent({
      cookie: [
        "sessionid=admin-session",
        "csrftoken=admin-csrf",
        "shopman_station_trust_pdv=station-1",
        "shopman_operator_sessionid=operator-session",
        "shopman_operator_csrftoken=operator-csrf",
      ].join("; "),
    });

    await proxyDjangoPath(event, "/api/v1/backstage/marketing/v2");

    expect(calls[0]?.options.headers.cookie).toBe(
      "shopman_station_trust_pdv=station-1; sessionid=operator-session; csrftoken=operator-csrf",
    );
    expect(calls[0]?.options.headers.cookie).not.toContain("admin-session");
    expect(calls[0]?.options.headers.cookie).not.toContain("admin-csrf");
  });

  it("chega sem autenticação de operador quando o browser tem apenas a sessão do Admin", async () => {
    const raw = vi.fn((url: string, options: RawCall["options"]) => {
      calls.push({ url, options });
      return Promise.resolve(upstream(403, {}, {}));
    });
    vi.stubGlobal("$fetch", Object.assign(vi.fn(), { raw }));
    const { event } = makeEvent({ cookie: "sessionid=admin-session; csrftoken=admin-csrf" });

    await proxyDjangoPath(event, "/api/v1/backstage/marketing/v2");

    expect(calls[0]?.options.headers.cookie).toBeUndefined();
  });

  it("reescreve o delete do logout sem apagar o cookie direto do Admin", async () => {
    const raw = vi.fn().mockResolvedValue(upstream(200, {}, {
      "set-cookie": "sessionid=; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Domain=.boulangerie.com.br; Path=/; Secure; HttpOnly; SameSite=Lax",
    }));
    vi.stubGlobal("$fetch", Object.assign(vi.fn(), { raw }));
    const { event, res } = makeEvent({
      cookie: "sessionid=admin-session; shopman_operator_sessionid=operator-session",
    });

    await proxyDjangoPath(event, "/api/v1/backstage/operator/lock");

    expect(raw.mock.calls[0]?.[1].headers.cookie).toBe("sessionid=operator-session");
    expect(res.getHeader("set-cookie")).toBe(
      "shopman_operator_sessionid=; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Domain=.boulangerie.com.br; Path=/; Secure; HttpOnly; SameSite=Lax",
    );
  });
});
