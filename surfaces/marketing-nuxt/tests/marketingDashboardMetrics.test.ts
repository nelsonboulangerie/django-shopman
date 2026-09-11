import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("métricas operacionais do painel", () => {
  it("renders ledger facts and never claims reach from accepted sends", () => {
    const page = readFileSync(
      new URL("../app/pages/index.vue", import.meta.url),
      "utf8",
    );

    expect(page).toContain("confirmed_targets_today");
    expect(page).toContain("accepted_unconfirmed_targets_today");
    expect(page).toContain("Aceitas, ainda sem confirmação");
    expect(page).toContain("unknown_targets_open");
    expect(page).not.toContain("audience_reached_today");
    expect(page).not.toContain("Clientes alcançados");
    expect(page).not.toContain("published_today");
  });
});
