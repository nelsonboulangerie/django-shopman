import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCampaignFireCommand } from "~/composables/useCampaignFireCommand";
import type { MarketingActionProjectionV2 } from "~/generated/marketingClient";
import type { Campaign } from "~/types/campaign";

const rule = {
  pk: 3,
  version: 7,
  name: "Fornada local",
  audience_rules: { tags: ["clientes-da-casa"] },
  is_active: true,
} as Campaign;

const action = {
  ref: "campaign:3:fire_campaign:v7",
  resource_ref: "campaign:3",
  kind: "fire_campaign",
  enabled: true,
  reason: "",
  href: "/api/v1/backstage/marketing/rules/3/fire/",
  method: "POST",
  idempotency: "required",
  confirmation: { token_required: true },
} as MarketingActionProjectionV2;

const challenge = {
  token: "fire-token",
  ref: "fire-confirmation",
  expires_at: "2026-09-10T11:05:00-03:00",
  mode: "typed" as const,
  step_up: "password" as const,
  dual_control: false,
  typed_phrase: "PUBLICAR 48",
  consequence: "creates_review_announcement",
  resource_ref: "campaign:3",
  base_version: 7,
  audience_count: 48,
  platforms: ["instagram"],
  scheduled_for: null,
};

const response = {
  ok: true as const,
  replayed: false,
  receipt: {
    ref: "fire-receipt",
    kind: "fire",
    state: "completed",
    base_version: 7,
    resulting_version: 8,
    resource_ref: "campaign:3",
    outcome: { audience_count: 48, announcement_ref: "announcement:77" },
    created_at: "2026-09-10T11:00:00-03:00",
    completed_at: "2026-09-10T11:00:01-03:00",
  },
  announcement: { pk: 77 },
};

beforeEach(() => {
  vi.restoreAllMocks();
  Object.assign(globalThis, {
    ref,
    flagMarketingSessionError: vi.fn(() => false),
  });
  vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
    "11111111-1111-4111-8111-111111111111",
  );
});

describe("comando seguro de disparo", () => {
  it("preserva versão, público e idempotência do challenge até o receipt", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce({
        data: { code: "confirmation_required", confirmation: challenge },
      })
      .mockResolvedValueOnce({ ok: true, step_up: {} })
      .mockResolvedValueOnce(response);
    Object.assign(globalThis, { $fetch: fetcher });
    const command = useCampaignFireCommand();
    const audience = { tags: ["clientes-da-casa"] };

    expect(await command.begin({ rule, action, audience })).toBeNull();
    expect(command.pendingCommand.value?.challenge).toEqual(challenge);
    expect(fetcher.mock.calls[0]![1]).toMatchObject({
      headers: { "Idempotency-Key": "11111111-1111-4111-8111-111111111111" },
      body: { base_version: 7, audience_rules: audience },
    });
    expect(fetcher.mock.calls[0]![1].body).not.toHaveProperty("body");

    const accepted = await command.confirm({
      credential: "senha-segura",
      typedConfirmation: "PUBLICAR 48",
    });

    expect(accepted.receipt.ref).toBe("fire-receipt");
    expect(fetcher.mock.calls[2]![1]).toMatchObject({
      headers: { "Idempotency-Key": "11111111-1111-4111-8111-111111111111" },
      body: {
        base_version: 7,
        audience_rules: audience,
        confirmation_token: "fire-token",
        typed_confirmation: "PUBLICAR 48",
      },
    });
    expect(command.pendingCommand.value).toBeNull();
  });

  it("sela o produto escolhido na intenção e o mostra durante a confirmação", async () => {
    const fetcher = vi.fn().mockRejectedValue({
      data: { code: "confirmation_required", confirmation: challenge },
    });
    Object.assign(globalThis, { $fetch: fetcher });
    const command = useCampaignFireCommand();

    expect(
      await command.begin({
        rule,
        action,
        audience: {},
        sku: "MDL",
        productLabel: "Madeleine (MDL)",
      }),
    ).toBeNull();

    expect(fetcher.mock.calls[0]![1].body).toEqual({
      base_version: 7,
      sku: "MDL",
    });
    expect(command.pendingCommand.value?.productLabel).toBe("Madeleine (MDL)");
  });

  it("recusa Action de outra versão antes de chamar a rede", async () => {
    const fetcher = vi.fn();
    Object.assign(globalThis, { $fetch: fetcher });
    const command = useCampaignFireCommand();

    await expect(
      command.begin({
        rule,
        action: { ...action, ref: "campaign:3:fire_campaign:v6" },
        audience: {},
      }),
    ).rejects.toThrow("marketing_fire_action_mismatch");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("reusa a mesma chave ao repetir a mesma intenção após throttle", async () => {
    const limited = {
      status: 429,
      data: { code: "throttled", detail: "Aguarde." },
    };
    const fetcher = vi.fn().mockRejectedValue(limited);
    Object.assign(globalThis, { $fetch: fetcher });
    const command = useCampaignFireCommand();

    await expect(command.begin({ rule, action, audience: {} })).rejects.toBe(limited);
    await expect(command.begin({ rule, action, audience: {} })).rejects.toBe(limited);

    expect(fetcher.mock.calls[0]![1].headers).toEqual(
      fetcher.mock.calls[1]![1].headers,
    );
    expect(globalThis.crypto.randomUUID).toHaveBeenCalledTimes(1);
  });

  it("recusa challenge de outra campanha sem pedir senha", async () => {
    const fetcher = vi.fn().mockRejectedValue({
      data: {
        code: "confirmation_required",
        confirmation: { ...challenge, resource_ref: "campaign:99" },
      },
    });
    Object.assign(globalThis, { $fetch: fetcher });
    const command = useCampaignFireCommand();

    await expect(
      command.begin({ rule, action, audience: {} }),
    ).rejects.toThrow("marketing_fire_confirmation_context_mismatch");
    expect(command.pendingCommand.value).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
