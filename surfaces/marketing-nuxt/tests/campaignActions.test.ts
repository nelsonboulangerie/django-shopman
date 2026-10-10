import { computed, ref } from "vue";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useCampaigns } from "~/composables/useCampaigns";
import {
  campaignEditAvailability,
  campaignPatchPayload,
  isExactCampaignEditAction,
} from "~/presentation/campaignActions";
import type {
  Campaign,
  MarketingActionProjectionV2,
  OptionsResponse,
  RulesResponse,
} from "~/types/campaign";

const rule = {
  pk: 3,
  version: 7,
  name: "Fornada artesanal",
  is_active: true,
  updated_at: "2026-09-28T10:00:00-03:00",
} as Campaign;

const editAction = {
  ref: "campaign:3:edit_campaign:v7",
  resource_ref: "campaign:3",
  kind: "edit_campaign",
  label: "Editar campanha",
  priority: "primary",
  enabled: true,
  reason: "",
  href: "/settings/campaigns#campaign-3",
  method: "GET",
  payload_schema: "",
  idempotency: "none",
  confirmation: {
    mode: "none",
    token_required: false,
    consequence_code: "",
    step_up: "none",
    dual_control: false,
  },
  eligible_count: 0,
  required_capabilities: ["shop.edit_marketing_campaigns"],
  creates_external_effect: false,
} as MarketingActionProjectionV2;

let rulesData: ReturnType<typeof ref<RulesResponse>>;
let optionsData: ReturnType<typeof ref<OptionsResponse>>;
const refresh = vi.fn();
const fetcher = vi.fn();
const sonner = {
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
};

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    ref,
    useFetch: (url: string) =>
      url.endsWith("/options/")
        ? {
            data: optionsData,
            refresh: vi.fn(),
            pending: ref(false),
            error: ref(null),
          }
        : { data: rulesData, refresh, pending: ref(false), error: ref(null) },
    $fetch: fetcher,
    useSonner: sonner,
    marketingSessionOnError: () => {},
    flagMarketingSessionError: () => false,
    httpError: (error: unknown) => error,
    httpErrorMessage: (_error: unknown, fallback: string) => fallback,
  });
});

beforeEach(() => {
  rulesData = ref({ rules: [{ ...rule }], actions: [{ ...editAction }] });
  optionsData = ref({ options: {} } as OptionsResponse);
  refresh.mockReset().mockResolvedValue(undefined);
  fetcher.mockReset().mockResolvedValue({ ok: true });
  sonner.error.mockReset();
  sonner.success.mockReset();
  sonner.warning.mockReset();
});

describe("Action de edição e CAS da campanha", () => {
  it("aceita somente a Action exata da campanha e da versão atuais", () => {
    expect(isExactCampaignEditAction(rule, editAction)).toBe(true);
    expect(
      isExactCampaignEditAction(rule, {
        ...editAction,
        ref: "campaign:3:edit_campaign:v6",
      }),
    ).toBe(false);
    expect(
      campaignEditAvailability(rule, [
        { ...editAction, enabled: false, reason: "missing_capability" },
      ]),
    ).toEqual({
      enabled: false,
      reason: "Seu perfil não autoriza alterações nesta campanha.",
    });
  });

  it("torna o relógio de leitura obrigatório no payload", () => {
    expect(campaignPatchPayload(rule, { is_active: false })).toEqual({
      is_active: false,
      base_updated_at: "2026-09-28T10:00:00-03:00",
    });
    expect(() =>
      campaignPatchPayload({ updated_at: "" }, { is_active: false }),
    ).toThrow("marketing_campaign_base_version_missing");
  });

  it("liga ou desliga com Action atual, CAS e recarga canônica", async () => {
    const campaigns = useCampaigns();

    expect(await campaigns.toggle(rule)).toBe(true);

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/backstage/marketing/rules/3/",
      {
        method: "PATCH",
        body: {
          is_active: false,
          base_updated_at: "2026-09-28T10:00:00-03:00",
        },
      },
    );
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(campaigns.mutatingCampaignPk.value).toBeNull();
  });

  it("falha fechado sem Action executável e não chama a rede", async () => {
    rulesData.value = { rules: [{ ...rule }], actions: [] };
    const campaigns = useCampaigns();

    expect(await campaigns.toggle(rule)).toBe(false);

    expect(fetcher).not.toHaveBeenCalled();
    expect(sonner.error).toHaveBeenCalledWith(
      "A ação segura de edição não está disponível. Atualize a lista.",
    );
  });

  it("recarrega no conflito sem fingir que o estado mudou", async () => {
    fetcher.mockRejectedValueOnce({
      status: 409,
      data: { code: "version_conflict" },
    });
    const campaigns = useCampaigns();

    expect(await campaigns.toggle(rule)).toBe(false);

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(sonner.warning).toHaveBeenCalledWith(
      "A campanha mudou em outra sessão. Compare as versões no formulário.",
    );
  });

  it("não duplica PATCH enquanto a primeira mutação está em voo", async () => {
    let release!: () => void;
    fetcher.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
    );
    const campaigns = useCampaigns();

    const first = campaigns.toggle(rule);
    expect(campaigns.mutatingCampaignPk.value).toBe(3);
    expect(await campaigns.toggle(rule)).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(1);

    release();
    expect(await first).toBe(true);
  });
});
