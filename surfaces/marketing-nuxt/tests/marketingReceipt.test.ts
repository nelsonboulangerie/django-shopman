import { describe, expect, it } from "vitest";
import {
  preserveMarketingReceipt,
  restoreMarketingReceipt,
} from "~/utils/marketingReceipt";
import type { MarketingCommandReceipt } from "~/types/campaign";

function receipt(
  over: Partial<MarketingCommandReceipt> = {},
): MarketingCommandReceipt {
  return {
    ref: "receipt-42",
    kind: "retry_delivery",
    state: "succeeded",
    base_version: 3,
    resulting_version: 4,
    resource_ref: "announcement:42",
    outcome: { queued_count: 2 },
    created_at: "2026-09-09T10:00:00-03:00",
    completed_at: "2026-09-09T10:00:01-03:00",
    ...over,
  };
}

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
}

describe("marketing receipt preservation", () => {
  it("restores the receipt beside the same announcement after route reload", () => {
    const storage = memoryStorage();

    expect(
      preserveMarketingReceipt(42, receipt(), { storage, now: 1_000 }),
    ).toBe(true);
    expect(restoreMarketingReceipt(42, { storage, now: 2_000 })).toEqual(
      receipt(),
    );
  });

  it("never crosses resources and removes expired evidence", () => {
    const storage = memoryStorage();

    expect(
      preserveMarketingReceipt(41, receipt(), { storage, now: 1_000 }),
    ).toBe(false);
    expect(
      preserveMarketingReceipt(42, receipt(), { storage, now: 1_000 }),
    ).toBe(true);
    expect(
      restoreMarketingReceipt(42, {
        storage,
        now: 1_000 + 24 * 60 * 60 * 1_000 + 1,
      }),
    ).toBeNull();
  });

  it("fails closed on malformed session data", () => {
    const storage = memoryStorage();
    storage.setItem("shopman:marketing:receipt:v1:announcement:42", "not-json");

    expect(restoreMarketingReceipt(42, { storage })).toBeNull();
  });
});
