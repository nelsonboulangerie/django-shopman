// Caixa pessoal de Marketing. O SSE só invalida; o fetch owner-scoped é a verdade.
import { notificationAction } from "~/presentation/notifications";
import type {
  MarketingNotification,
  MarketingNotificationsResponse,
} from "~/types/notifications";

export const NOTIFICATION_REVISION_STATE = "marketing-notification-revision";
const POLL_MS = 60_000;

export function useMarketingNotificationInbox() {
  const config = useRuntimeConfig();
  const revision = useState<number>(NOTIFICATION_REVISION_STATE, () => 0);
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  const mutationError = ref("");
  const acknowledging = ref<ReadonlySet<number>>(new Set());
  const markingSeen = ref(false);
  const { data, refresh, pending, error } =
    useFetch<MarketingNotificationsResponse>(
      "/api/v1/backstage/notifications/v2/?limit=100",
      {
        key: "marketing-notifications-v2",
        server: true,
        onResponseError: operatorSessionOnError,
      },
    );

  const notifications = computed<MarketingNotification[]>(
    () => data.value?.notifications ?? [],
  );
  const unseenCount = computed(() => data.value?.counts.unseen ?? 0);
  const unresolvedCount = computed(() => data.value?.counts.unresolved ?? 0);
  const shopTimezone = computed(() => data.value?.shop_timezone ?? "UTC");
  const hasMore = computed(() => data.value?.page.has_more ?? false);
  let source: EventSource | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  async function reconcile() {
    revision.value += 1;
    await refresh();
  }

  function connect() {
    if (source) return;
    const url = ssePath("/sse/notifications", config.app.baseURL);
    try {
      realtime.value = "connecting";
      source = new EventSource(url, { withCredentials: true });
      ["message", "user-notification"].forEach((name) =>
        source!.addEventListener(name, () => void reconcile()),
      );
      source.onopen = () => {
        const reconnected = realtime.value === "polling";
        realtime.value = "live";
        if (reconnected) void reconcile();
      };
      source.onerror = () => { realtime.value = "polling"; };
    } catch {
      source = null;
      realtime.value = "polling";
    }
  }

  const onVisible = () => {
    if (document.visibilityState === "visible") void reconcile();
  };

  onMounted(() => {
    connect();
    pollTimer = setInterval(() => void reconcile(), POLL_MS);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (source) source.close();
    source = null;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  async function markVisible(): Promise<boolean> {
    if (markingSeen.value) return false;
    const ids = notifications.value
      .filter(
        (notification) =>
          notification.lifecycle === "unseen" &&
          notificationAction(notification, "mark_notification_seen")?.enabled,
      )
      .map((notification) => notification.pk);
    if (!ids.length) return true;

    markingSeen.value = true;
    mutationError.value = "";
    try {
      await $fetch("/api/v1/backstage/notifications/v2/seen/", {
        method: "POST",
        body: { notification_ids: ids },
      });
      await refresh();
      return true;
    } catch (caught) {
      flagMarketingSessionError(caught);
      mutationError.value = httpErrorMessage(
        caught,
        "Não foi possível registrar quais alertas você viu.",
      );
      return false;
    } finally {
      markingSeen.value = false;
    }
  }

  async function acknowledge(
    notification: MarketingNotification,
  ): Promise<boolean> {
    if (acknowledging.value.has(notification.pk)) return false;
    const action = notificationAction(notification, "acknowledge_notification");
    if (!action?.enabled) {
      mutationError.value = action
        ? "Este alerta não pode ser assumido agora."
        : "O alerta mudou. Atualize antes de continuar.";
      return false;
    }

    acknowledging.value = new Set([...acknowledging.value, notification.pk]);
    mutationError.value = "";
    try {
      await $fetch(action.href, { method: "POST", body: {} });
      await refresh();
      return true;
    } catch (caught) {
      flagMarketingSessionError(caught);
      mutationError.value = httpErrorMessage(
        caught,
        "Não foi possível assumir este alerta. Ele continua pendente.",
      );
      return false;
    } finally {
      const next = new Set(acknowledging.value);
      next.delete(notification.pk);
      acknowledging.value = next;
    }
  }

  function openHref(notification: MarketingNotification): string | null {
    mutationError.value = "";
    const action = notificationAction(notification, "open_announcement");
    if (!action?.enabled) {
      mutationError.value = action
        ? "Seu acesso não permite abrir este anúncio."
        : "O alerta mudou. Atualize antes de abrir.";
      return null;
    }
    return action.href;
  }

  return {
    notifications,
    unseenCount,
    unresolvedCount,
    shopTimezone,
    hasMore,
    realtime,
    loading: pending,
    error,
    mutationError,
    acknowledging,
    markingSeen,
    refresh: reconcile,
    markVisible,
    acknowledge,
    openHref,
  };
}
