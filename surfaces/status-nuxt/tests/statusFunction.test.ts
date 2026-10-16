import { afterEach, describe, expect, it, vi } from "vitest";

import { onRequestGet } from "../functions/api/status";

const run = async () => {
  const response = await (onRequestGet as (context: { env: Record<string, string> }) => Promise<Response>)({ env: {} });
  return { response, body: await response.json() };
};

describe("Cloudflare public status projection", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reports operational only when both independent probes answer successfully", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 200 })));

    const { response, body } = await run();

    expect(response.headers.get("cache-control")).toContain("s-maxage=30");
    expect(body.overall).toBe("operational");
    expect(body.components.map((component: { id: string }) => component.id)).toEqual([
      "online_store",
      "service_operations",
    ]);
    expect(JSON.stringify(body)).not.toMatch(/database|redis|pool|migration|queue/i);
  });

  it("fails closed when a probe is down", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response("{}", { status: 200 }))
      .mockResolvedValueOnce(new Response("{}", { status: 503 })));

    const { body } = await run();

    expect(body.overall).toBe("outage");
    expect(body.components[1].status).toBe("outage");
  });

  it("does not call a non-server response healthy", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response("{}", { status: 200 }))
      .mockResolvedValueOnce(new Response("{}", { status: 401 })));

    const { body } = await run();

    expect(body.overall).toBe("unknown");
    expect(body.components[1].status).toBe("unknown");
  });
});
