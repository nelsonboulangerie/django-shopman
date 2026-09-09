import { describe, expect, it } from "vitest";
import { buildApprovalCommand } from "~/composables/useCampaignBoard";

describe("approval command consequence", () => {
  it("makes the now CTA authoritative even with a stale schedule value", () => {
    expect(
      buildApprovalCommand(
        { body: "Saiu do forno", publish_at: "2026-09-08T18:00" },
        7,
        "now",
        "America/Sao_Paulo",
      ),
    ).toEqual({
      body: "Saiu do forno",
      publish_timezone: "America/Sao_Paulo",
      base_version: 7,
      publish_mode: "now",
    });
  });

  it("carries one explicit instant only for the scheduled CTA", () => {
    expect(
      buildApprovalCommand(
        { body: "Saiu do forno", publish_at: "2026-09-08T18:00:00-03:00" },
        7,
        "scheduled",
        "America/Sao_Paulo",
      ),
    ).toEqual({
      body: "Saiu do forno",
      publish_at: "2026-09-08T18:00:00-03:00",
      publish_timezone: "America/Sao_Paulo",
      base_version: 7,
      publish_mode: "scheduled",
    });
  });

  it("never invents a schedule when the explicit instant is absent", () => {
    expect(() => buildApprovalCommand(
      { body: "Oi" },
      7,
      "scheduled",
      "America/Sao_Paulo",
    )).toThrow(
      "requires publish_at",
    );
  });

  it("fails closed when the backend-owned timezone is absent", () => {
    expect(() => buildApprovalCommand({ body: "Oi" }, 7, "now", "")).toThrow(
      "requires the shop timezone",
    );
  });
});
