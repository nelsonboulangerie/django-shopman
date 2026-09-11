import { computed, ref } from "vue";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useMarketingNotificationInbox } from "~/composables/useMarketingNotificationInbox";
import type { MarketingActionProjectionV2 } from "~/types/campaign";
import type {
  MarketingNotification,
  MarketingNotificationsResponse,
} from "~/types/notifications";

let response: ReturnType<typeof ref<MarketingNotificationsResponse>>;
const refresh = vi.fn();
const fetcher = vi.fn();
const states = new Map<string, ReturnType<typeof ref>>();

function action(
  kind: MarketingActionProjectionV2["kind"],
  href: string,
  resourceRef: string,
): MarketingActionProjectionV2 {
  return {
    ref: `${resourceRef}:${kind}`,
    resource_ref: resourceRef,
    kind,
    label: kind,
    priority: "primary",
    enabled: true,
    reason: "",
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

function row(
  pk: number,
  lifecycle: MarketingNotification["lifecycle"],
): MarketingNotification {
  return {
    pk,
    category: "marketing_approval",
    title: "Revisão necessária",
    message: "Confira o anúncio.",
    lifecycle,
    severity: "action_required",
    source: {
      condition: "announcement_review",
      ref: "announcement:42",
      version: 3,
    },
    owner: { user_id: 9, role: "product" },
    escalation: { role: "ops", at: null },
    expires_at: null,
    seen_at: null,
    acknowledged_at: null,
    resolved_at: null,
    version: 1,
    created_at: "2026-09-09T09:00:00-03:00",
    created_at_display: "09/09 às 09:00",
    actions: [
      action(
        "open_announcement",
        "/announcements/42#review",
        "announcement:42",
      ),
      action(
        "mark_notification_seen",
        `/api/v1/backstage/notifications/${pk}/read/`,
        `notification:${pk}`,
      ),
      action(
        "acknowledge_notification",
        `/api/v1/backstage/notifications/${pk}/acknowledge/`,
        `notification:${pk}`,
      ),
    ],
  };
}

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    flagMarketingSessionError: () => false,
    onBeforeUnmount: () => {},
    onMounted: () => {},
    operatorSessionOnError: () => {},
    ref,
    useRuntimeConfig: () => ({ app: { baseURL: "/" } }),
    useState: (key: string, init: () => unknown) => {
      if (!states.has(key)) states.set(key, ref(init()));
      return states.get(key)!;
    },
    useFetch: () => ({
      data: response,
      refresh,
      pending: ref(false),
      error: ref(null),
    }),
    $fetch: fetcher,
    ssePath: (path: string) => path,
    httpErrorMessage: (_error: unknown, fallback: string) => fallback,
  });
});

beforeEach(() => {
  Object.assign(globalThis, {
    onBeforeUnmount: () => {},
    onMounted: () => {},
  });
  states.clear();
  refresh.mockReset().mockResolvedValue(undefined);
  fetcher.mockReset().mockResolvedValue({});
  response = ref({
    schema_version: 2,
    shop_timezone: "America/Sao_Paulo",
    as_of: "2026-09-09T09:00:00-03:00",
    notifications: [row(1, "unseen"), row(2, "seen")],
    page: { limit: 100, has_more: false, next_cursor: "" },
    counts: { unseen: 1, unresolved: 2 },
  });
});

describe("useMarketingNotificationInbox", () => {
  it("marks only visible unseen canonical alerts in one owner-scoped batch", async () => {
    response.value.notifications.push({
      ...row(3, "unseen"),
      actions: [
        action(
          "mark_notification_seen",
          "/api/v1/backstage/notifications/999/read/",
          "notification:3",
        ),
      ],
    });
    const box = useMarketingNotificationInbox();

    await box.markVisible();

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/backstage/notifications/v2/seen/",
      { method: "POST", body: { notification_ids: [1] } },
    );
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(box.unresolvedCount.value).toBe(2);
  });

  it("keeps the alert and an actionable error when acknowledgement fails", async () => {
    fetcher.mockRejectedValueOnce(new Error("network"));
    const box = useMarketingNotificationInbox();

    expect(await box.acknowledge(response.value.notifications[0]!)).toBe(false);

    expect(box.notifications.value).toHaveLength(2);
    expect(box.mutationError.value).toContain("continua pendente");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("refuses a stored open URL that no longer matches its source", () => {
    const box = useMarketingNotificationInbox();
    const unsafe = {
      ...response.value.notifications[0]!,
      actions: [
        action(
          "open_announcement",
          "/announcements/99#review",
          "announcement:42",
        ),
      ],
    };

    expect(box.openHref(unsafe)).toBeNull();
    expect(box.mutationError.value).toContain("mudou");
  });

  it("treats SSE as an invalidation and refetches the canonical owner view", async () => {
    vi.useFakeTimers();
    let mounted: (() => void) | undefined;
    let unmounted: (() => void) | undefined;
    const listeners = new Map<string, () => void>();
    const close = vi.fn();
    class FakeEventSource {
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;

      constructor(
        public url: string,
        public options: { withCredentials: boolean },
      ) {}

      addEventListener(name: string, callback: () => void) {
        listeners.set(name, callback);
      }

      close = close;
    }
    const addDocumentListener = vi.fn();
    const removeDocumentListener = vi.fn();
    const addWindowListener = vi.fn();
    const removeWindowListener = vi.fn();
    Object.assign(globalThis, {
      onMounted: (callback: () => void) => {
        mounted = callback;
      },
      onBeforeUnmount: (callback: () => void) => {
        unmounted = callback;
      },
      EventSource: FakeEventSource,
      document: {
        visibilityState: "visible",
        addEventListener: addDocumentListener,
        removeEventListener: removeDocumentListener,
      },
      window: {
        addEventListener: addWindowListener,
        removeEventListener: removeWindowListener,
      },
    });
    const box = useMarketingNotificationInbox();

    mounted!();
    listeners.get("user-notification")!();
    await Promise.resolve();

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(states.get("marketing-notification-revision")?.value).toBe(1);
    expect(box.notifications.value).toEqual(response.value.notifications);
    expect(addDocumentListener).toHaveBeenCalledWith(
      "visibilitychange",
      expect.any(Function),
    );
    expect(addWindowListener).toHaveBeenCalledWith(
      "online",
      expect.any(Function),
    );

    unmounted!();
    expect(close).toHaveBeenCalledTimes(1);
    expect(removeDocumentListener).toHaveBeenCalledTimes(1);
    expect(removeWindowListener).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
