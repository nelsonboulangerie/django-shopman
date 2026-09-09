import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMarketingDecisionCommand } from "~/composables/useMarketingDecisionCommand";

const challenge = {
  token: "approval-token",
  ref: "approval-ref",
  expires_at: "2026-09-09T11:05:00-03:00",
  mode: "typed" as const,
  step_up: "password" as const,
  dual_control: false,
  typed_phrase: "PUBLICAR 12",
  consequence: "publishes_now_to_eligible_audience",
  resource_ref: "announcement:42",
  base_version: 7,
  audience_count: 12,
  platforms: ["instagram"],
  scheduled_for: null,
};

const response = {
  ok: true as const,
  replayed: false,
  receipt: {
    ref: "decision-receipt",
    kind: "approve",
    state: "succeeded",
    base_version: 7,
    resulting_version: 8,
    resource_ref: "announcement:42",
    outcome: { publish_mode: "now" },
    created_at: "2026-09-09T11:00:00-03:00",
    completed_at: "2026-09-09T11:00:01-03:00",
  },
  announcement: {},
};

beforeEach(() => {
  Object.assign(globalThis, { ref });
});

describe("Marketing decision confirmation", () => {
  it("preserves the exact edited command across the server-issued challenge", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce({
        data: { code: "confirmation_required", confirmation: challenge },
      })
      .mockResolvedValueOnce({ ok: true, step_up: {} })
      .mockResolvedValueOnce(response);
    Object.assign(globalThis, { $fetch: fetcher });
    const command = useMarketingDecisionCommand();
    const body = {
      body: "Fornada pronta",
      platforms: ["instagram"],
      publish_mode: "now",
      publish_timezone: "America/Sao_Paulo",
      base_version: 7,
    };

    expect(
      await command.begin({
        announcementId: 42,
        action: "approve",
        body,
        idempotencyKey: "same-decision-key",
      }),
    ).toBeNull();
    expect(command.pendingDecision.value?.challenge).toEqual(challenge);

    const confirmed = await command.confirm({
      credential: "senha-segura",
      typedConfirmation: "PUBLICAR 12",
    });

    expect(confirmed.receipt.ref).toBe("decision-receipt");
    expect(fetcher.mock.calls[2]).toEqual([
      "/api/v1/backstage/marketing/announcements/42/approve/",
      {
        method: "POST",
        headers: { "Idempotency-Key": "same-decision-key" },
        body: {
          ...body,
          confirmation_token: "approval-token",
          typed_confirmation: "PUBLICAR 12",
        },
      },
    ]);
    expect(command.pendingDecision.value).toBeNull();
  });

  it("rejects a challenge issued for another resource before any step-up", async () => {
    const fetcher = vi.fn().mockRejectedValue({
      data: {
        code: "confirmation_required",
        confirmation: { ...challenge, resource_ref: "announcement:99" },
      },
    });
    Object.assign(globalThis, { $fetch: fetcher });
    const command = useMarketingDecisionCommand();

    await expect(
      command.begin({
        announcementId: 42,
        action: "approve",
        body: { base_version: 7, publish_mode: "now" },
        idempotencyKey: "mismatch-key",
      }),
    ).rejects.toThrow("marketing_confirmation_context_mismatch");
    expect(command.pendingDecision.value).toBeNull();
  });

  it("keeps dual control mandatory", async () => {
    const fetcher = vi.fn().mockRejectedValueOnce({
      data: {
        code: "confirmation_required",
        confirmation: { ...challenge, dual_control: true, step_up: "totp" },
      },
    });
    Object.assign(globalThis, { $fetch: fetcher });
    const command = useMarketingDecisionCommand();
    await command.begin({
      announcementId: 42,
      action: "approve",
      body: { base_version: 7, publish_mode: "now" },
      idempotencyKey: "dual-key",
    });

    await expect(
      command.confirm({
        credential: "123456",
        typedConfirmation: "PUBLICAR 12",
      }),
    ).rejects.toThrow("marketing_dual_control_required");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
