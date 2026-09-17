// Probes do BFF servidos pela layer: `/health/live` (processo, sem Django) e
// `/health/ready` (inclui o Django). Exercita a regra pura, as ROTAS reais da
// layer e a fronteira com os oito consumidores — nenhum pode sombrear a rota com
// uma cópia local, e todos precisam declarar o upstream que o `ready` consulta.
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createApp, eventHandler, toWebHandler, type EventHandler } from "h3";
import { afterEach, describe, expect, it, vi } from "vitest";

import liveRoute from "../server/routes/health/live.get";
import readyRoute from "../server/routes/health/ready.get";
import {
  checkDjangoReadiness,
  ProbeRateLimiter,
} from "../server/utils/healthProbe";

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OPERATOR_APPS = [
  "pos-nuxt",
  "kds-nuxt",
  "orders-nuxt",
  "production-nuxt",
  "purchase-nuxt",
  "marketing-nuxt",
  "bi-nuxt",
  "hub-nuxt",
] as const;

afterEach(() => {
  vi.unstubAllGlobals();
});

function serve(route: EventHandler) {
  return toWebHandler(createApp().use(eventHandler((event) => route(event))));
}

describe("operator BFF health chain", () => {
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

describe("layer route /health/live", () => {
  it("answers alive without touching the Django upstream or runtime config", async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error("Django is down"));
    const runtimeConfig = vi.fn(() => {
      throw new Error("liveness must not read the upstream");
    });
    vi.stubGlobal("fetch", fetchSpy);
    vi.stubGlobal("useRuntimeConfig", runtimeConfig);

    const response = await serve(liveRoute)(new Request("http://mkt.test/health/live"));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok", checks: { bff: "ok" } });
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.get("content-type")).toContain("application/json");
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(runtimeConfig).not.toHaveBeenCalled();
  });
});

describe("layer route /health/ready", () => {
  it("is ready when the Django readiness answers 200", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    vi.stubGlobal("useRuntimeConfig", () => ({ djangoBaseUrl: "http://django.internal:8000" }));

    const response = await serve(readyRoute)(new Request("http://mkt.test/health/ready"));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok", checks: { bff: "ok", api: "ok" } });
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(fetchSpy).toHaveBeenCalledWith(
      "http://django.internal:8000/health/ready/",
      expect.objectContaining({ redirect: "error" }),
    );
  });

  it.each([
    ["Django not ready", () => Promise.resolve({ status: 503 })],
    ["Django unreachable", () => Promise.reject(new Error("ECONNREFUSED django.internal"))],
  ])("fails with 503 when %s", async (_label, upstream) => {
    vi.stubGlobal("fetch", vi.fn(upstream));
    vi.stubGlobal("useRuntimeConfig", () => ({ djangoBaseUrl: "http://django.internal:8000" }));

    const response = await serve(readyRoute)(new Request("http://mkt.test/health/ready"));
    const body = await response.text();

    expect(response.status).toBe(503);
    expect(JSON.parse(body)).toEqual({ status: "fail", checks: { bff: "ok", api: "fail" } });
    expect(body).not.toContain("django.internal");
  });

  it("fails closed and sanitized when the upstream is not configured", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    vi.stubGlobal("useRuntimeConfig", () => ({ djangoBaseUrl: "" }));

    const response = await serve(readyRoute)(new Request("http://mkt.test/health/ready"));
    const body = await response.text();

    expect(response.status).toBe(503);
    expect(JSON.parse(body)).toEqual({ status: "fail", checks: { bff: "ok", api: "fail" } });
    expect(body).not.toContain("configured");
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe.each(OPERATOR_APPS)("consumidor %s serve os probes pela layer", (app) => {
  const appDir = resolve(surfacesDir, app);
  const nuxtConfig = readFileSync(resolve(appDir, "nuxt.config.ts"), "utf8");

  it("estende a layer que registra /health/live e /health/ready", () => {
    expect(nuxtConfig).toMatch(/extends:\s*\[\s*["']\.\.\/operator-kit["']\s*\]/);
  });

  it("não sombreia a rota da layer com uma cópia local", () => {
    expect(existsSync(resolve(appDir, "server/routes/health"))).toBe(false);
    expect(existsSync(resolve(appDir, "server/utils/healthProbe.ts"))).toBe(false);
  });

  it("declara o upstream Django que o /health/ready consulta", () => {
    expect(nuxtConfig).toMatch(/\bdjangoBaseUrl\b/);
  });
});
