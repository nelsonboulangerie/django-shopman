import { defineComponent, h } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { registerEndpoint } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useWebPush } from "../../app/composables/useWebPush";

const endpoint = "https://push.invalid/local-fixture";
const methods: string[] = [];
registerEndpoint("/api/v1/backstage/notifications/push/", (event) => {
  methods.push(event.method);
  return {
    devices: [
      {
        id: 1,
        endpoint,
        surface_ref: "kds",
        device_label: "Teste",
        categories: ["kitchen"],
        created_at: "",
        last_success_at: null,
      },
    ],
    categories: [],
    surface_categories: {},
  };
});
const originalNotification = Object.getOwnPropertyDescriptor(
  window,
  "Notification",
);
const originalPushManager = Object.getOwnPropertyDescriptor(
  window,
  "PushManager",
);
const originalServiceWorker = Object.getOwnPropertyDescriptor(
  navigator,
  "serviceWorker",
);
let previousRuntime: Record<string, unknown> | null = null;
const mounted: Array<{ unmount(): void }> = [];
afterEach(() => {
  for (const w of mounted.splice(0)) w.unmount();
  for (const [object, key, descriptor] of [
    [window, "Notification", originalNotification],
    [window, "PushManager", originalPushManager],
    [navigator, "serviceWorker", originalServiceWorker],
  ] as const) {
    if (descriptor) Object.defineProperty(object, key, descriptor);
    else Reflect.deleteProperty(object, key);
  }
  methods.length = 0;
  if (previousRuntime) {
    const runtime = useRuntimeConfig().public as Record<string, unknown>;
    for (const key of ["operatorPwa", "vapidPublicKey"]) {
      if (previousRuntime[key] === undefined) delete runtime[key];
      else runtime[key] = previousRuntime[key];
    }
    previousRuntime = null;
  }
  vi.restoreAllMocks();
});

async function setupPush() {
  const runtime = useRuntimeConfig().public as Record<string, unknown>;
  previousRuntime = {
    operatorPwa: runtime.operatorPwa,
    vapidPublicKey: runtime.vapidPublicKey,
  };
  runtime.operatorPwa = {
    push: { surfaceRef: "kds", categories: ["kitchen"] },
  };
  runtime.vapidPublicKey = "local-fixture";
  let push!: ReturnType<typeof useWebPush>;
  const w = mount(
    defineComponent({
      setup() {
        push = useWebPush();
        return () => h("div");
      },
    }),
  );
  mounted.push(w);
  await flushPromises();
  return { w, push };
}

describe("permissão atual dos avisos", () => {
  it("ao voltar dos ajustes com permissão revogada, deixa de dizer que os avisos estão ligados", async () => {
    const requestPermission = vi.fn();
    const subscribe = vi.fn();
    const notification = {
      permission: "granted" as NotificationPermission,
      requestPermission,
    };
    Object.defineProperty(window, "Notification", {
      configurable: true,
      value: notification,
    });
    Object.defineProperty(window, "PushManager", {
      configurable: true,
      value: class {},
    });
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        ready: Promise.resolve({
          pushManager: {
            getSubscription: vi.fn(async () => ({ endpoint })),
            subscribe,
          },
        }),
      },
    });
    const { w, push } = await setupPush();
    await vi.waitFor(() => expect(push.active.value).toBe(true));
    notification.permission = "denied";
    window.dispatchEvent(new Event("focus"));
    expect(push.permission.value).toBe("denied");
    expect(push.active.value).toBe(false);
    expect(requestPermission).not.toHaveBeenCalled();
    expect(subscribe).not.toHaveBeenCalled();
    expect(methods.every((method) => method === "GET")).toBe(true);
    notification.permission = "granted";
    await push.refresh();
    expect(push.active.value).toBe(true);
    w.unmount();
    mounted.splice(mounted.indexOf(w), 1);
    notification.permission = "denied";
    window.dispatchEvent(new Event("focus"));
    expect(push.permission.value).toBe("granted");
  });

  it("sem API de notificações, foco não solicita permissões nem inventa suporte", async () => {
    Reflect.deleteProperty(window, "Notification");
    Reflect.deleteProperty(window, "PushManager");
    const { push } = await setupPush();
    window.dispatchEvent(new Event("focus"));
    expect(push.supported.value).toBe(false);
    expect(push.active.value).toBe(false);
    expect(push.permission.value).toBe("default");
    expect(methods).toEqual([]);
  });
});
