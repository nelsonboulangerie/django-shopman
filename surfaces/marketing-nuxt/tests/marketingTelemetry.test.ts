import {
  buildMarketingVital,
  marketingRoute,
  marketingVitalRating,
  reportMarketingVital,
} from "../app/utils/marketingTelemetry";

describe("Marketing telemetry privacy/cardinality boundary", () => {
  it("maps paths to bounded route labels without refs or query", () => {
    expect(marketingRoute("/?customer=42")).toBe("board");
    expect(marketingRoute("/announcements/secret-ref?token=x")).toBe("announcement_detail");
    expect(marketingRoute("/anything/private-value")).toBe("other");
  });

  it("uses the agreed pilot thresholds", () => {
    expect(marketingVitalRating("LCP", 2500)).toBe("good");
    expect(marketingVitalRating("LCP", 2501)).toBe("needs_improvement");
    expect(marketingVitalRating("INP", 501)).toBe("poor");
    expect(marketingVitalRating("CLS", 0.1)).toBe("good");
  });

  it("builds only a bounded PII-free sample", () => {
    expect(buildMarketingVital("LCP", 1843.4422, "/campaigns?customer=1", true)).toEqual({
      name: "LCP",
      value: 1843.442,
      rating: "good",
      route: "campaigns",
      theme: "dark",
    });
    expect(buildMarketingVital("INP", Number.NaN, "/", false)).toBeNull();
  });

  it("posts through the BFF and never makes telemetry an operator error", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("$fetch", fetch);
    const sample = buildMarketingVital("CLS", 0.04, "/", false)!;

    await expect(reportMarketingVital(sample)).resolves.toBe(true);
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/backstage/marketing/telemetry/vital/",
      { method: "POST", body: sample },
    );

    fetch.mockRejectedValueOnce(new Error("offline"));
    await expect(reportMarketingVital(sample)).resolves.toBe(false);
  });
});
