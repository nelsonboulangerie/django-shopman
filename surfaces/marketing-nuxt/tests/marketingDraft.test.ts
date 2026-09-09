import { beforeEach, describe, expect, it } from "vitest";
import {
  MARKETING_DRAFT_TTL_MS,
  clearMarketingDraft,
  marketingDraftKey,
  mergeMarketingDraft,
  readMarketingDraft,
  writeMarketingDraft,
} from "~/utils/marketingDraft";
import type { DraftStorage } from "~/utils/marketingDraft";

class MemoryStorage implements DraftStorage {
  rows = new Map<string, string>();

  getItem(key: string) { return this.rows.get(key) ?? null; }
  setItem(key: string, value: string) { this.rows.set(key, value); }
  removeItem(key: string) { this.rows.delete(key); }
}

const alice = { owner: "operator:7", resource: "announcement:42" };
let storage: MemoryStorage;

beforeEach(() => { storage = new MemoryStorage(); });

describe("marketing draft storage", () => {
  it("isolates drafts by operator and resource", () => {
    writeMarketingDraft(storage, alice, 1, { body: "base" }, { body: "Alice" }, 100);

    expect(readMarketingDraft(storage, alice, 101)?.payload).toEqual({ body: "Alice" });
    expect(readMarketingDraft(storage, { ...alice, owner: "operator:8" }, 101)).toBeNull();
    expect(readMarketingDraft(storage, { ...alice, resource: "announcement:43" }, 101)).toBeNull();
    expect(marketingDraftKey(alice)).not.toContain(" ");
  });

  it("expires after seven days and removes corrupted state", () => {
    writeMarketingDraft(storage, alice, 1, { body: "base" }, { body: "draft" }, 100);
    expect(readMarketingDraft(storage, alice, 100 + MARKETING_DRAFT_TTL_MS)).toBeNull();

    storage.setItem(marketingDraftKey(alice), "not-json");
    expect(readMarketingDraft(storage, alice, 101)).toBeNull();
    expect(storage.getItem(marketingDraftKey(alice))).toBeNull();
  });

  it("clears only the committed resource", () => {
    const other = { owner: alice.owner, resource: "campaign:new" };
    writeMarketingDraft(storage, alice, 1, {}, { body: "draft" });
    writeMarketingDraft(storage, other, "new", {}, { name: "draft" });

    clearMarketingDraft(storage, alice);

    expect(readMarketingDraft(storage, alice)).toBeNull();
    expect(readMarketingDraft(storage, other)?.payload).toEqual({ name: "draft" });
  });
});

describe("marketing draft three-way merge", () => {
  it("combines independent local and server changes with no question", () => {
    const merged = mergeMarketingDraft(
      { body: "base", platforms: ["instagram"] },
      { body: "server", platforms: ["instagram"] },
      { body: "base", platforms: ["instagram", "whatsapp"] },
    );

    expect(merged.conflicts).toEqual([]);
    expect(merged.localWins).toEqual({
      body: "server",
      platforms: ["instagram", "whatsapp"],
    });
    expect(merged.serverWins).toEqual(merged.localWins);
  });

  it("shows only overlapping fields and preserves every independent edit", () => {
    const merged = mergeMarketingDraft(
      { body: "base", hashtags: "#base", platforms: ["instagram"] },
      { body: "server", hashtags: "#base", platforms: ["instagram", "google"] },
      { body: "local", hashtags: "#local", platforms: ["instagram"] },
    );

    expect(merged.conflicts.map(conflict => conflict.field)).toEqual(["body"]);
    expect(merged.localWins).toEqual({
      body: "local",
      hashtags: "#local",
      platforms: ["instagram", "google"],
    });
    expect(merged.serverWins).toEqual({
      body: "server",
      hashtags: "#local",
      platforms: ["instagram", "google"],
    });
  });
});
