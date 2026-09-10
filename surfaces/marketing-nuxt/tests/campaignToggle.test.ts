import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("campaign activation switch", () => {
  it("keeps a 44px touch target without stretching the visual track", () => {
    const page = readFileSync(
      new URL("../app/pages/campaigns.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain(
      'class="-ml-2 grid size-11 shrink-0 place-items-center rounded-md"',
    );
    expect(page).toContain(
      'class="flex h-5 w-9 items-center rounded-full transition-colors"',
    );
    expect(page).toContain('role="switch"');
    expect(page).toContain(':aria-checked="rule.is_active"');
  });

  it("never opens a server-disabled manual fire action", () => {
    const page = readFileSync(
      new URL("../app/pages/campaigns.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain(':disabled="!fireAction(rule)?.enabled"');
    expect(page).toContain('action.kind === "fire_campaign"');
    expect(page).toContain('"Indisponível"');
  });

  it("keeps the open editor across the authentication gate", () => {
    const page = readFileSync(
      new URL("../app/pages/campaigns.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain('useState<boolean>("marketing-campaign-creating"');
    expect(page).toContain('"marketing-campaign-editing-pk"');
    expect(page).not.toContain("const creating = ref(false)");
    expect(page).not.toContain("const editing = ref<Campaign | null>(null)");
  });
});
