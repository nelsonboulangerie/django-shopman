import { describe, expect, it, vi } from "vitest";
import { configureFlowCommand } from "~/composables/useWhatsAppTemplate";

describe("platform configuration command", () => {
  it("reuses one key and exact version through server challenge and TOTP", async () => {
    const challenge = {
      data: {
        code: "confirmation_required",
        confirmation: {
          token: "server-token",
          step_up: "totp",
          typed_phrase: "",
        },
      },
    };
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(challenge)
      .mockResolvedValueOnce({ ok: true, step_up: {} })
      .mockResolvedValueOnce({
        ok: true,
        replayed: false,
        receipt: { ref: "receipt-1", resulting_version: 8 },
      });

    const result = await configureFlowCommand(
      fetcher as unknown as typeof $fetch,
      {
        flowNs: "content_active",
        baseVersion: 7,
        totp: "123456",
        idempotencyKey: "same-command-key",
      },
    );

    expect(result.receipt.resulting_version).toBe(8);
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      headers: { "Idempotency-Key": "same-command-key" },
      body: { flow_ns: "content_active", base_version: 7 },
    });
    expect(fetcher.mock.calls[1]).toEqual([
      "/api/v1/backstage/marketing/security/step-up/",
      { method: "POST", body: { method: "totp", credential: "123456" } },
    ]);
    expect(fetcher.mock.calls[2]?.[1]).toMatchObject({
      headers: { "Idempotency-Key": "same-command-key" },
      body: {
        flow_ns: "content_active",
        base_version: 7,
        confirmation_token: "server-token",
      },
    });
  });

  it("does not turn provider outage into a confirmation attempt", async () => {
    const outage = {
      data: { code: "platform_catalog_unavailable", retryable: true },
    };
    const fetcher = vi.fn().mockRejectedValue(outage);

    await expect(
      configureFlowCommand(fetcher as unknown as typeof $fetch, {
        flowNs: "content_last_known",
        baseVersion: 3,
        totp: "123456",
        idempotencyKey: "outage-command-key",
      }),
    ).rejects.toBe(outage);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
