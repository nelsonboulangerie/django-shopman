import { afterEach, describe, expect, it, vi } from "vitest";

import { onRequestGet } from "../functions/api/watchman-readiness";

const run = async (env: Record<string, string> = {}) => {
  const response = await (onRequestGet as (context: { env: Record<string, string> }) => Promise<Response>)({ env });
  return { response, body: await response.json() };
};

describe("Cloudflare composite readiness", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("returns 200 only after both readiness legs pass", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { response, body } = await run();

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(body.status).toBe("ok");
    expect(body.failedChecks).toEqual([]);
    expect(body.checks).toEqual([
      { id: "web_operator", status: "operational" },
      { id: "web_storefront", status: "operational" },
    ]);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://api.boulangerie.com.br/health/ready/",
      "https://api.boulangerie.com.br/api/v1/health/ready/",
    ]);
  });

  it("returns 503 and identifies the failed leg without proxying upstream details", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (
      url.includes("api/v1")
        ? new Response('{"database":"secret detail"}', { status: 503 })
        : new Response("{}", { status: 200 })
    )));

    const { response, body } = await run();

    expect(response.status).toBe(503);
    expect(body.status).toBe("unavailable");
    expect(body.failedChecks).toEqual(["web_storefront"]);
    expect(body.checks).toEqual([
      { id: "web_operator", status: "operational" },
      { id: "web_storefront", status: "outage" },
    ]);
    expect(JSON.stringify(body)).not.toMatch(/database|secret detail|redis|pool|migration|queue/i);
  });

  it("fails closed on transport and non-success responses", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.includes("operator.example")) throw new Error("network down");
      return new Response("{}", { status: 401 });
    }));

    const { response, body } = await run({
      OPERATIONS_READINESS_URL: "https://operator.example/ready",
      STOREFRONT_READINESS_URL: "https://storefront.example/ready",
    });

    expect(response.status).toBe(503);
    expect(body.failedChecks).toEqual(["web_operator", "web_storefront"]);
    expect(body.checks).toEqual([
      { id: "web_operator", status: "outage" },
      { id: "web_storefront", status: "unknown" },
    ]);
  });

  it("aborts both parallel probes after four seconds and fails closed", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })));

    const pending = run();
    await vi.advanceTimersByTimeAsync(3_999);
    expect(vi.getTimerCount()).toBe(2);
    await vi.advanceTimersByTimeAsync(1);
    const { response, body } = await pending;

    expect(response.status).toBe(503);
    expect(body.failedChecks).toEqual(["web_operator", "web_storefront"]);
    expect(vi.getTimerCount()).toBe(0);
  });
});
