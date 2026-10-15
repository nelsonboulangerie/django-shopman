import { describe, expect, it } from "vitest";

import type { PublicStatusSnapshot } from "../app/types/status";
import { safeSnapshot, statusIsFresh } from "../app/utils/statusPresentation";

const observedAt = "2026-10-15T15:00:00.000Z";
const snapshot: PublicStatusSnapshot = {
  schemaVersion: 1,
  overall: "operational",
  observedAt,
  components: [
    { id: "online_store", label: "Loja online", description: "Loja", status: "operational" },
  ],
};

describe("public status freshness", () => {
  it("keeps a recent proof green", () => {
    const now = Date.parse(observedAt) + 30_000;
    expect(statusIsFresh(snapshot, now)).toBe(true);
    expect(safeSnapshot(snapshot, now).overall).toBe("operational");
  });

  it("never leaves stale evidence green", () => {
    const now = Date.parse(observedAt) + 180_000;
    const stale = safeSnapshot(snapshot, now);
    expect(stale.overall).toBe("unknown");
    expect(stale.components[0]?.status).toBe("unknown");
  });

  it("rejects evidence dated implausibly in the future", () => {
    const now = Date.parse(observedAt) - 30_000;
    expect(statusIsFresh(snapshot, now)).toBe(false);
  });
});
