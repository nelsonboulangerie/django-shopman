import { mount } from "@vue/test-utils";
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import MarketingNotificationsBell from "~/components/MarketingNotificationsBell.vue";
import type { MarketingActionProjectionV2 } from "~/types/campaign";
import type { MarketingNotification } from "~/types/notifications";

const markVisible = vi.fn();
const acknowledge = vi.fn();
const openHref = vi.fn();
const refresh = vi.fn();
const navigate = vi.fn();
const mutationError = ref("");
const acknowledging = ref<ReadonlySet<number>>(new Set());

function action(
  kind: MarketingActionProjectionV2["kind"],
  href: string,
  resourceRef: string,
  enabled = true,
): MarketingActionProjectionV2 {
  return {
    ref: `${resourceRef}:${kind}`,
    resource_ref: resourceRef,
    kind,
    label: kind,
    priority: "primary",
    enabled,
    reason: enabled ? "" : "missing_capability",
    href,
    method: kind === "open_announcement" ? "GET" : "POST",
    payload_schema: "none",
    idempotency: "none",
    confirmation: {
      mode: "none",
      token_required: false,
      consequence_code: "",
      step_up: "none",
      dual_control: false,
    },
    eligible_count: 1,
    required_capabilities: [],
    creates_external_effect: false,
  };
}

function notification(
  over: Partial<MarketingNotification> = {},
): MarketingNotification {
  return {
    pk: 7,
    category: "marketing_approval",
    title: "Revisão necessária",
    message: "Confira o anúncio antes de publicar.",
    lifecycle: "seen",
    severity: "action_required",
    source: {
      condition: "announcement_review",
      ref: "announcement:42",
      version: 3,
    },
    owner: { user_id: 9, role: "product" },
    escalation: { role: "ops", at: null },
    expires_at: "2026-09-09T13:00:00-03:00",
    seen_at: "2026-09-09T09:01:00-03:00",
    acknowledged_at: null,
    resolved_at: null,
    version: 2,
    created_at: "2026-09-09T09:00:00-03:00",
    created_at_display: "09/09 às 09:00",
    actions: [
      action(
        "open_announcement",
        "/announcements/42#review",
        "announcement:42",
      ),
      action(
        "acknowledge_notification",
        "/api/v1/backstage/notifications/7/acknowledge/",
        "notification:7",
      ),
    ],
    ...over,
  };
}

const notifications = ref<MarketingNotification[]>([notification()]);

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    nextTick,
    onBeforeUnmount,
    onMounted,
    ref,
    navigateTo: navigate,
    useUserNotifications: () => ({
      notifications,
      unseenCount: ref(0),
      unresolvedCount: ref(1),
      shopTimezone: ref("America/Sao_Paulo"),
      hasMore: ref(false),
      realtime: ref("live"),
      loading: ref(false),
      error: ref(null),
      mutationError,
      acknowledging,
      markingSeen: ref(false),
      refresh,
      markVisible,
      acknowledge,
      openHref,
    }),
  });
});

beforeEach(() => {
  markVisible.mockReset().mockResolvedValue(true);
  acknowledge.mockReset().mockResolvedValue(true);
  openHref.mockReset().mockReturnValue("/announcements/42#review");
  refresh.mockReset().mockResolvedValue(undefined);
  navigate.mockReset().mockResolvedValue(undefined);
  mutationError.value = "";
  acknowledging.value = new Set();
  notifications.value = [notification()];
});

function bell() {
  return mount(MarketingNotificationsBell, {
    attachTo: document.body,
    global: { stubs: { Icon: true, Teleport: true } },
  });
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("MarketingNotificationsBell", () => {
  it("behaves as a modal, isolates the page and restores trigger focus", async () => {
    const appRoot = document.createElement("div");
    appRoot.dataset.marketingAppRoot = "";
    document.body.append(appRoot);
    const wrapper = bell();
    const trigger = wrapper.get<HTMLButtonElement>(
      'button[aria-controls="marketing-notifications-panel"]',
    );
    trigger.element.focus();

    await trigger.trigger("click");
    await nextTick();
    const panel = wrapper.get("#marketing-notifications-panel");
    expect(panel.attributes("role")).toBe("dialog");
    expect(panel.attributes("aria-modal")).toBe("true");
    expect(appRoot.hasAttribute("inert")).toBe(true);
    expect(document.activeElement?.id).toBe("marketing-notifications-title");

    await panel.trigger("keydown", { key: "Escape" });
    await nextTick();
    expect(appRoot.hasAttribute("inert")).toBe(false);
    expect(document.activeElement).toBe(trigger.element);
    appRoot.remove();
  });

  it("opens in one gesture, marks visible alerts and keeps seen unresolved", async () => {
    const wrapper = bell();
    const trigger = wrapper.get(
      'button[aria-controls="marketing-notifications-panel"]',
    );

    expect(trigger.attributes("aria-label")).toContain("1 pendentes, 0 novos");
    await trigger.trigger("click");

    expect(markVisible).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("1 pendente");
    expect(wrapper.text()).toContain("Visto");
    expect(wrapper.text()).not.toContain("Aprovar");
    expect(wrapper.text()).not.toContain("Recusar");
  });

  it("uses the validated exact deep-link as its single review action", async () => {
    const wrapper = bell();
    await wrapper
      .get('button[aria-controls="marketing-notifications-panel"]')
      .trigger("click");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Revisar anúncio")!
      .trigger("click");

    expect(openHref).toHaveBeenCalledWith(notifications.value[0]);
    expect(navigate).toHaveBeenCalledWith("/announcements/42#review");
    expect(wrapper.find("#marketing-notifications-panel").exists()).toBe(false);
  });

  it("shows missing capability inline and never calls an unavailable action", async () => {
    notifications.value = [
      notification({
        actions: [
          action(
            "open_announcement",
            "/announcements/42#review",
            "announcement:42",
            false,
          ),
        ],
      }),
    ];
    const wrapper = bell();
    await wrapper
      .get('button[aria-controls="marketing-notifications-panel"]')
      .trigger("click");
    const review = wrapper
      .findAll("button")
      .find((button) => button.text() === "Revisar anúncio")!;

    expect((review.element as HTMLButtonElement).disabled).toBe(true);
    expect(wrapper.text()).toContain("Seu acesso não permite");
    expect(openHref).not.toHaveBeenCalled();
  });

  it("keeps a failed mutation visible beside the still-pending alert", async () => {
    mutationError.value =
      "Não foi possível assumir. O alerta continua pendente.";
    const wrapper = bell();
    await wrapper
      .get('button[aria-controls="marketing-notifications-panel"]')
      .trigger("click");

    expect(wrapper.text()).toContain("continua pendente");
    expect(wrapper.text()).toContain("Revisão necessária");
    expect(wrapper.get('[role="alert"]').text()).toContain("continua pendente");
  });
});
