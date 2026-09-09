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
});
