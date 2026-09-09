import { describe, expect, it, vi } from "vitest";
import {
  assertRecoveryAction,
  beginMarketingRecovery,
  confirmMarketingRecovery,
} from "~/composables/useMarketingRecovery";
import type {
  MarketingActionProjectionV2,
  MarketingCommandResponse,
  MarketingConfirmationChallenge,
} from "~/types/campaign";

function action(
  over: Partial<MarketingActionProjectionV2> = {},
): MarketingActionProjectionV2 {
  return {
    ref: "announcement:42:retry_failed_delivery:v3",
    resource_ref: "announcement:42",
    kind: "retry_failed_delivery",
    label: "presentation.marketing.action.retry_failed_delivery",
    priority: "primary",
    enabled: true,
    reason: "",
    href: "/api/v1/backstage/marketing/announcements/42/retry-deliveries/",
    method: "POST",
    payload_schema: "marketing.command.retry-delivery.v2",
    idempotency: "required",
    confirmation: {
      mode: "typed",
      token_required: true,
      consequence_code: "retries_only_failed_retryable_targets",
      step_up: "password",
      dual_control: false,
    },
    eligible_count: 2,
    required_capabilities: ["shop.retry_failed_marketing"],
    creates_external_effect: true,
    ...over,
  };
}

function challenge(
  over: Partial<MarketingConfirmationChallenge> = {},
): MarketingConfirmationChallenge {
  return {
    token: "server-token",
    ref: "confirmation-ref",
    expires_at: "2026-09-09T10:05:00-03:00",
    mode: "typed",
    step_up: "password",
    dual_control: false,
    typed_phrase: "PUBLICAR 2",
    consequence: "retries_only_failed_retryable_targets",
    resource_ref: "announcement:42",
    base_version: 3,
    audience_count: 2,
    platforms: ["whatsapp"],
    scheduled_for: null,
    ...over,
  };
}

function response(): MarketingCommandResponse {
  return {
    ok: true,
    replayed: false,
    receipt: {
      ref: "receipt-ref",
      kind: "retry_delivery",
      state: "succeeded",
      base_version: 3,
      resulting_version: 4,
      resource_ref: "announcement:42",
      outcome: { queued_count: 2 },
      created_at: "2026-09-09T10:00:00-03:00",
      completed_at: "2026-09-09T10:00:01-03:00",
    },
    announcement: {} as MarketingCommandResponse["announcement"],
  };
}

describe("Marketing recovery commands", () => {
  it("opens the exact server challenge without changing key or version", async () => {
    const serverChallenge = challenge();
    const fetcher = vi.fn().mockRejectedValue({
      data: { code: "confirmation_required", confirmation: serverChallenge },
    });

    const result = await beginMarketingRecovery(
      fetcher as unknown as typeof $fetch,
      action(),
      { announcementId: 42, baseVersion: 3, idempotencyKey: "same-key" },
    );

    expect(result).toEqual({ kind: "challenge", challenge: serverChallenge });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/backstage/marketing/announcements/42/retry-deliveries/",
      {
        method: "POST",
        headers: { "Idempotency-Key": "same-key" },
        body: { base_version: 3 },
      },
    );
  });

  it("uses the operator phrase and step-up, then consumes that same challenge", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, step_up: {} })
      .mockResolvedValueOnce(response());

    const result = await confirmMarketingRecovery(
      fetcher as unknown as typeof $fetch,
      action(),
      challenge(),
      { credential: "senha-segura", typedConfirmation: "PUBLICAR 2" },
      { announcementId: 42, baseVersion: 3, idempotencyKey: "same-key" },
    );

    expect(result.receipt.ref).toBe("receipt-ref");
    expect(fetcher.mock.calls).toEqual([
      [
        "/api/v1/backstage/marketing/security/step-up/",
        {
          method: "POST",
          body: { method: "password", credential: "senha-segura" },
        },
      ],
      [
        "/api/v1/backstage/marketing/announcements/42/retry-deliveries/",
        {
          method: "POST",
          headers: { "Idempotency-Key": "same-key" },
          body: {
            base_version: 3,
            confirmation_token: "server-token",
            typed_confirmation: "PUBLICAR 2",
          },
        },
      ],
    ]);
  });

  it("blocks Action href tampering and never turns unknown into a blind retry", async () => {
    const fetcher = vi.fn();
    const tampered = action({ href: "https://evil.invalid/retry" });

    expect(() => assertRecoveryAction(tampered, 42)).toThrow(
      "unsafe_marketing_recovery_action",
    );
    await expect(
      beginMarketingRecovery(fetcher as unknown as typeof $fetch, tampered, {
        announcementId: 42,
        baseVersion: 3,
        idempotencyKey: "safe-key",
      }),
    ).rejects.toThrow("unsafe_marketing_recovery_action");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("does not bypass a dual-control gate in one browser session", async () => {
    const fetcher = vi.fn();

    await expect(
      confirmMarketingRecovery(
        fetcher as unknown as typeof $fetch,
        action(),
        challenge({ dual_control: true, step_up: "totp" }),
        { credential: "123456", typedConfirmation: "PUBLICAR 2" },
        { announcementId: 42, baseVersion: 3, idempotencyKey: "dual-key" },
      ),
    ).rejects.toThrow("marketing_dual_control_required");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("cancels through the exact cancel Action without unnecessary step-up", async () => {
    const cancelAction = action({
      ref: "announcement:42:cancel_announcement:v3",
      kind: "cancel_announcement",
      href: "/api/v1/backstage/marketing/announcements/42/cancel/",
      confirmation: {
        mode: "summary",
        token_required: true,
        consequence_code: "cancels_only_reversible_delivery_lanes",
        step_up: "none",
        dual_control: false,
      },
      creates_external_effect: false,
    });
    const cancelChallenge = challenge({
      mode: "summary",
      step_up: "none",
      typed_phrase: "",
      consequence: "cancels_only_reversible_delivery_lanes",
    });
    const cancelled = response();
    cancelled.receipt.kind = "cancel";
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce({
        data: {
          code: "confirmation_required",
          confirmation: cancelChallenge,
        },
      })
      .mockResolvedValueOnce(cancelled);
    const options = {
      announcementId: 42,
      baseVersion: 3,
      idempotencyKey: "cancel-key",
    };

    const started = await beginMarketingRecovery(
      fetcher as unknown as typeof $fetch,
      cancelAction,
      options,
    );
    expect(started.kind).toBe("challenge");
    await confirmMarketingRecovery(
      fetcher as unknown as typeof $fetch,
      cancelAction,
      cancelChallenge,
      {},
      options,
    );

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[1]?.[0]).toBe(
      "/api/v1/backstage/marketing/announcements/42/cancel/",
    );
  });

  it("reconciles unknown through TOTP and a lookup-only Action", async () => {
    const reconcileAction = action({
      ref: "announcement:42:reconcile_unknown_delivery:v3",
      kind: "reconcile_unknown_delivery",
      href: "/api/v1/backstage/marketing/announcements/42/reconcile-deliveries/",
      confirmation: {
        mode: "summary",
        token_required: true,
        consequence_code: "looks_up_unknown_without_resend",
        step_up: "totp",
        dual_control: false,
      },
      creates_external_effect: false,
    });
    const reconcileChallenge = challenge({
      mode: "summary",
      step_up: "totp",
      typed_phrase: "",
      consequence: "looks_up_unknown_without_resend",
    });
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, step_up: {} })
      .mockResolvedValueOnce(response());

    await confirmMarketingRecovery(
      fetcher as unknown as typeof $fetch,
      reconcileAction,
      reconcileChallenge,
      { credential: "123456" },
      { announcementId: 42, baseVersion: 3, idempotencyKey: "lookup-key" },
    );

    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      body: { method: "totp", credential: "123456" },
    });
    expect(fetcher.mock.calls[1]?.[0]).toBe(
      "/api/v1/backstage/marketing/announcements/42/reconcile-deliveries/",
    );
  });
});
