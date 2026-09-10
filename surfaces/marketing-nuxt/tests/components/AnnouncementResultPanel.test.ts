import { mount, flushPromises } from "@vue/test-utils";
import { computed, defineComponent, ref } from "vue";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import AnnouncementResultPanel from "~/components/AnnouncementResultPanel.vue";
import type {
  AnnouncementProjectionV2,
  MarketingActionProjectionV2,
  MarketingCommandResponse,
} from "~/types/campaign";

const SlotStub = defineComponent({ template: "<div><slot /></div>" });
const DialogStub = defineComponent({
  props: { open: Boolean },
  template: '<div v-if="open"><slot /></div>',
});

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    ref,
    httpErrorMessage: (_error: unknown, fallback: string) => fallback,
    useSonner: { success: vi.fn(), error: vi.fn() },
    useNuxtData: () => ({
      data: ref({ operator: { username: "admin", name: "Admin" } }),
    }),
  });
});

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
    "00000000-0000-4000-8000-000000000035",
  );
});

function counts(over: Record<string, number> = {}) {
  return {
    planned: 0,
    suppressed: 0,
    queued: 0,
    sending: 0,
    accepted: 0,
    confirmed: 0,
    failed_retryable: 0,
    failed_final: 0,
    unknown: 0,
    cancelled: 0,
    expired: 0,
    ...over,
  };
}

function announcement(
  over: Partial<AnnouncementProjectionV2> = {},
): AnnouncementProjectionV2 {
  return {
    ref: "announcement:42",
    version: 3,
    state: "failed",
    reason_code: "",
    facts: {
      trigger: "manual",
      campaign_ref: "campaign:1",
      template_ref: "template:1",
      product_ref: "",
      promotion_ref: "",
      link_ref: "",
      content_as_of: null,
      content_fresh_until: null,
      content_facts_hash: "a".repeat(64),
      fact_variable_refs: [],
    },
    platform_refs: ["whatsapp", "instagram"],
    created_at: "2026-09-09T09:00:00-03:00",
    age_seconds: 3600,
    expires_at: null,
    expires_in_seconds: null,
    scheduled_for: null,
    approved_at: "2026-09-09T09:01:00-03:00",
    rejected_at: null,
    published_at: null,
    settled_at: "2026-09-09T09:05:00-03:00",
    audience: {
      source_ref: "audience:1",
      version: 1,
      eligible_count: 3,
      excluded_by_reason: {},
      deduplicated_count: 3,
      vip_count: 0,
      general_count: 3,
      wave_count: 1,
      policy_version: "2026-09",
      cohort_hash: "b".repeat(64),
      calculated_at: "2026-09-09T09:00:00-03:00",
      expires_at: null,
      freshness: {
        state: "fresh",
        as_of: "2026-09-09T09:00:00-03:00",
        degraded_sources: [],
      },
    },
    artifact: null,
    readiness: { state: "ready", platforms: [] },
    delivery: {
      state: "completed_with_failures",
      counts: counts({ confirmed: 1, failed_retryable: 1, unknown: 1 }),
      target_count: 3,
      fanout_expected: 3,
      fanout_materialized: 3,
      platforms: [
        {
          platform_ref: "whatsapp",
          state: "completed_with_failures",
          counts: counts({ confirmed: 1, failed_retryable: 1 }),
          target_count: 2,
          fanout_expected: 2,
          fanout_materialized: 2,
          lane_count: 1,
          complete_lane_count: 1,
        },
        {
          platform_ref: "instagram",
          state: "unknown",
          counts: counts({ unknown: 1 }),
          target_count: 1,
          fanout_expected: 1,
          fanout_materialized: 1,
          lane_count: 1,
          complete_lane_count: 1,
        },
      ],
      freshness: {
        state: "fresh",
        as_of: "2026-09-09T09:05:00-03:00",
        degraded_sources: [],
      },
    },
    ...over,
  };
}

function retryAction(): MarketingActionProjectionV2 {
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
    eligible_count: 1,
    required_capabilities: ["shop.retry_failed_marketing"],
    creates_external_effect: true,
  };
}

function cancelAction(): MarketingActionProjectionV2 {
  return {
    ...retryAction(),
    ref: "announcement:42:cancel_announcement:v3",
    kind: "cancel_announcement",
    href: "/api/v1/backstage/marketing/announcements/42/cancel/",
    payload_schema: "marketing.command.cancel.v2",
    creates_external_effect: false,
    confirmation: {
      mode: "summary",
      token_required: true,
      consequence_code: "cancels_only_reversible_delivery_lanes",
      step_up: "none",
      dual_control: false,
    },
  };
}

function response(): MarketingCommandResponse {
  return {
    ok: true,
    replayed: false,
    receipt: {
      ref: "receipt-result",
      kind: "retry_delivery",
      state: "succeeded",
      base_version: 3,
      resulting_version: 4,
      resource_ref: "announcement:42",
      outcome: { queued_count: 1 },
      created_at: "2026-09-09T09:06:00-03:00",
      completed_at: "2026-09-09T09:06:01-03:00",
    },
    announcement: {} as MarketingCommandResponse["announcement"],
  };
}

function panel(options: { actions?: MarketingActionProjectionV2[] } = {}) {
  return mount(AnnouncementResultPanel, {
    props: {
      announcement: announcement(),
      actions: options.actions ?? [retryAction()],
      shopTimezone: "America/Sao_Paulo",
      receipt: {
        ...response().receipt,
        ref: "receipt-before",
        kind: "approve",
      },
    },
    global: {
      stubs: {
        Icon: true,
        UiDialog: DialogStub,
        UiDialogContent: SlotStub,
        UiDialogHeader: SlotStub,
        UiDialogTitle: SlotStub,
        UiDialogDescription: SlotStub,
        UiDialogFooter: SlotStub,
      },
    },
  });
}

describe("AnnouncementResultPanel", () => {
  it("keeps receipt, partial and unknown evidence together", () => {
    const wrapper = panel();

    expect(wrapper.text()).toContain("Entrega parcial");
    expect(wrapper.text()).toContain("receipt-before");
    expect(wrapper.text()).toContain("1 entrega confirmada");
    expect(wrapper.text()).toContain("1 falha que pode ser tentada novamente");
    expect(wrapper.text()).toContain("1 resultado incerto");
    expect(wrapper.text()).toContain("não são reenviados");
    expect(wrapper.text()).toContain("Comprovante:");
    expect(wrapper.text()).toContain("concluído");
    expect(wrapper.text()).not.toContain("Receipt:");
    expect(wrapper.text()).not.toContain("succeeded");
  });

  it("explains a rejected decision without suggesting a delivery or cancellation", () => {
    const wrapper = mount(AnnouncementResultPanel, {
      props: {
        announcement: announcement({
          state: "rejected",
          delivery: {
            ...announcement().delivery,
            state: "not_started",
            counts: counts(),
            target_count: 0,
            fanout_expected: 0,
            fanout_materialized: 0,
            platforms: [],
          },
        }),
        actions: [],
        shopTimezone: "America/Sao_Paulo",
      },
      global: {
        stubs: {
          Icon: true,
          UiDialog: DialogStub,
          UiDialogContent: SlotStub,
          UiDialogHeader: SlotStub,
          UiDialogTitle: SlotStub,
          UiDialogDescription: SlotStub,
          UiDialogFooter: SlotStub,
        },
      },
    });

    expect(wrapper.text()).toContain("Anúncio recusado");
    expect(wrapper.text()).toContain("sem criar entregas");
    expect(wrapper.text()).not.toContain("A entrega ainda não começou");
    expect(wrapper.text()).not.toContain("Resultado por plataforma");
  });

  it("deduplicates double click and consumes the exact challenge", async () => {
    const confirmation = {
      token: "server-token",
      ref: "confirmation-ref",
      expires_at: "2026-09-09T09:10:00-03:00",
      mode: "typed",
      step_up: "password",
      dual_control: false,
      typed_phrase: "PUBLICAR 1",
      consequence: "retries_only_failed_retryable_targets",
      resource_ref: "announcement:42",
      base_version: 3,
      audience_count: 1,
      platforms: ["whatsapp"],
      scheduled_for: null,
    };
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce({
        data: { code: "confirmation_required", confirmation },
      })
      .mockResolvedValueOnce({ ok: true, step_up: {} })
      .mockResolvedValueOnce(response());
    Object.assign(globalThis, { $fetch: fetcher });
    const wrapper = panel();
    const actionButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Tentar novamente 1 falha"))!;

    await Promise.all([
      actionButton.trigger("click"),
      actionButton.trigger("click"),
    ]);
    await flushPromises();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("PUBLICAR 1");
    expect(
      (wrapper.find("#recovery-username").element as HTMLInputElement).value,
    ).toBe("admin");
    expect(wrapper.find("#recovery-username").attributes("autocomplete")).toBe(
      "username",
    );

    await wrapper.find("#recovery-typed-confirmation").setValue("PUBLICAR 1");
    await wrapper.find("#recovery-credential").setValue("senha-segura");
    const confirmButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Confirmar consequência"))!;
    await confirmButton.trigger("click");
    await flushPromises();

    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(wrapper.emitted("receipt")?.[0]?.[0]).toEqual(response());
    expect(wrapper.emitted("refresh")).toHaveLength(1);
  });

  it("collects and preserves a cancellation reason before requesting confirmation", async () => {
    const confirmation = {
      token: "cancel-token",
      ref: "cancel-confirmation-ref",
      expires_at: "2026-09-09T09:10:00-03:00",
      mode: "summary",
      step_up: "none",
      dual_control: false,
      typed_phrase: "",
      consequence: "cancels_only_reversible_delivery_lanes",
      resource_ref: "announcement:42",
      base_version: 3,
      audience_count: 1,
      platforms: ["whatsapp"],
      scheduled_for: "2026-09-09T20:40:00-03:00",
    };
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce({
        data: { code: "confirmation_required", confirmation },
      })
      .mockResolvedValueOnce(response());
    Object.assign(globalThis, { $fetch: fetcher });
    const wrapper = panel({ actions: [cancelAction()] });
    const actionButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Cancelar"))!;

    await actionButton.trigger("click");
    await flushPromises();
    expect(fetcher).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Motivo do cancelamento");

    const reviewButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Conferir cancelamento"))!;
    expect(reviewButton.attributes("disabled")).toBeDefined();

    await wrapper
      .find("#recovery-cancel-reason")
      .setValue("Horário alterado pelo operador");
    await reviewButton.trigger("click");
    await flushPromises();

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      body: {
        base_version: 3,
        reason: "Horário alterado pelo operador",
      },
    });

    const confirmButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Confirmar consequência"))!;
    await confirmButton.trigger("click");
    await flushPromises();

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({
      body: {
        base_version: 3,
        reason: "Horário alterado pelo operador",
        confirmation_token: "cancel-token",
      },
    });
  });
});
