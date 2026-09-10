import { describe, expect, it, vi } from "vitest";

import {
  checkDjangoReadiness,
  ProbeRateLimiter,
} from "../server/utils/healthProbe";

describe("Marketing BFF health chain", () => {
  it("reports BFF and Django ready without reading or relaying the public body", async () => {
    const json = vi.fn();
    const fetchImpl = vi.fn().mockResolvedValue({ status: 200, json });

    const result = await checkDjangoReadiness(
      "https://api.example.test/base/",
      fetchImpl as unknown as typeof fetch,
    );

    expect(result).toEqual({
      status: "ok",
      checks: { bff: "ok", api: "ok" },
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      "https://api.example.test/health/ready/",
      expect.objectContaining({
        cache: "no-store",
        redirect: "error",
        signal: expect.any(AbortSignal),
      }),
    );
    expect(json).not.toHaveBeenCalled();
  });

  it("sanitizes an API dependency failure", async () => {
    const text = vi.fn();
    const fetchImpl = vi.fn().mockResolvedValue({ status: 503, text });

    await expect(
      checkDjangoReadiness(
        "https://api.example.test",
        fetchImpl as unknown as typeof fetch,
      ),
    ).resolves.toEqual({
      status: "fail",
      checks: { bff: "ok", api: "fail" },
    });
    expect(text).not.toHaveBeenCalled();
  });

  it("turns timeout/network errors into fail without throwing", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error("secret host"));

    await expect(
      checkDjangoReadiness(
        "https://api.example.test",
        fetchImpl as unknown as typeof fetch,
        10,
      ),
    ).resolves.toEqual({
      status: "fail",
      checks: { bff: "ok", api: "fail" },
    });
  });

  it("limits probes in bounded local memory and resets the window", () => {
    let now = 100;
    const limiter = new ProbeRateLimiter(2, 60, 2, () => now);

    expect(limiter.allow("a")).toBe(true);
    expect(limiter.allow("a")).toBe(true);
    expect(limiter.allow("a")).toBe(false);
    expect(limiter.allow("b")).toBe(true);
    expect(limiter.allow("c")).toBe(true);
    expect(limiter.trackedClients).toBe(2);
    now += 60;
    expect(limiter.allow("a")).toBe(true);
  });
});
