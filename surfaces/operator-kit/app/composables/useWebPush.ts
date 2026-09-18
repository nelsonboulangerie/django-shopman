interface OperatorPushConfig {
  surfaceRef: "hub" | "orders" | "pos" | "production" | "marketing" | "purchase" | "bi";
  categories: string[];
}

export interface PushDevice {
  id: number;
  endpoint: string;
  surface_ref: string;
  device_label: string;
  categories: string[];
  created_at: string;
  last_success_at: string | null;
}

interface PushDevicesResponse {
  devices: PushDevice[];
  categories: Array<{ value: string; label: string }>;
  surface_categories: Record<string, string[]>;
}

function applicationServerKey(value: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const decoded = atob((value + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index++) bytes[index] = decoded.charCodeAt(index);
  return bytes;
}

function defaultDeviceLabel(): string {
  if (!import.meta.client) return "Este aparelho";
  const platform = navigator.userAgentData?.platform || navigator.platform || "Aparelho";
  return `${platform} · ${new Date().toLocaleDateString("pt-BR")}`.slice(0, 120);
}

export function useWebPush() {
  const runtime = useRuntimeConfig().public as Record<string, unknown>;
  const pwa = (runtime.operatorPwa || {}) as { push?: OperatorPushConfig };
  const config = pwa.push;
  const vapidPublicKey = String(runtime.vapidPublicKey || "");
  const devices = ref<PushDevice[]>([]);
  const categories = ref<PushDevicesResponse["categories"]>([]);
  const currentEndpoint = ref("");
  const permission = ref<NotificationPermission>(
    import.meta.client && "Notification" in window ? Notification.permission : "default",
  );
  const loading = ref(false);
  const error = ref("");

  const supported = computed(() => Boolean(
    import.meta.client
    && config
    && vapidPublicKey
    && "serviceWorker" in navigator
    && "PushManager" in window
    && "Notification" in window,
  ));
  const currentDevice = computed(() => devices.value.find(device => device.endpoint === currentEndpoint.value) || null);
  const active = computed(() => permission.value === "granted" && currentDevice.value !== null);

  async function browserSubscription(): Promise<PushSubscription | null> {
    if (!supported.value) return null;
    const registration = await navigator.serviceWorker.ready;
    return registration.pushManager.getSubscription();
  }

  async function refresh(): Promise<void> {
    if (!config) return;
    try {
      const [response, subscription] = await Promise.all([
        $fetch<PushDevicesResponse>("/api/v1/backstage/notifications/push/"),
        browserSubscription(),
      ]);
      devices.value = response.devices || [];
      categories.value = response.categories || [];
      currentEndpoint.value = subscription?.endpoint || "";
      error.value = "";
    } catch {
      error.value = "Não foi possível consultar os avisos deste aparelho.";
    }
  }

  async function saveSubscription(subscription: PushSubscription): Promise<void> {
    if (!config) return;
    await $fetch("/api/v1/backstage/notifications/push/", {
      method: "POST",
      body: {
        subscription: subscription.toJSON(),
        surface_ref: config.surfaceRef,
        device_label: defaultDeviceLabel(),
        categories: config.categories,
      },
    });
    currentEndpoint.value = subscription.endpoint;
  }

  async function activate(): Promise<boolean> {
    if (!supported.value || !config) {
      error.value = vapidPublicKey ? "Este navegador não oferece avisos em segundo plano." : "Avisos ainda não foram habilitados neste ambiente.";
      return false;
    }
    loading.value = true;
    try {
      permission.value = await Notification.requestPermission();
      if (permission.value !== "granted") {
        error.value = "A permissão de avisos não foi concedida.";
        return false;
      }
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription()
        || await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: applicationServerKey(vapidPublicKey),
        });
      await saveSubscription(subscription);
      await refresh();
      return true;
    } catch {
      error.value = "Não foi possível ativar os avisos neste aparelho.";
      return false;
    } finally {
      loading.value = false;
    }
  }

  async function updateCategories(device: PushDevice, next: string[]): Promise<void> {
    await $fetch("/api/v1/backstage/notifications/push/", {
      method: "PATCH",
      body: { id: device.id, categories: next },
    });
    await refresh();
  }

  async function removeDevice(device: PushDevice): Promise<void> {
    await $fetch("/api/v1/backstage/notifications/push/", {
      method: "DELETE",
      body: { id: device.id },
    });
    if (device.endpoint === currentEndpoint.value) {
      const subscription = await browserSubscription();
      await subscription?.unsubscribe();
      currentEndpoint.value = "";
    }
    await refresh();
  }

  async function syncExisting(): Promise<void> {
    if (!supported.value || Notification.permission !== "granted") return;
    const subscription = await browserSubscription();
    await refresh();
    // Não sobrescrever preferências já gravadas a cada montagem. Só reassociar
    // quando o browser tem assinatura, mas este usuário ainda não a enxerga.
    if (subscription && !currentDevice.value) {
      await saveSubscription(subscription);
      await refresh();
    }
  }

  onMounted(() => void syncExisting());
  return { supported, active, permission, loading, error, devices, categories, currentDevice, refresh, activate, updateCategories, removeDevice };
}
