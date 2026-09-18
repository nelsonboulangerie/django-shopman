import { defineEventHandler, setResponseHeader } from "h3";

export const OPERATOR_PUSH_WORKER = String.raw`
const SHOPMAN_PUSH_API = "/api/v1/backstage/notifications/push/";

function shopmanSafeActionUrl(value) {
  if (typeof value !== "string") return self.location.origin + "/";
  try {
    const url = new URL(value, self.location.origin);
    return url.protocol === "https:" || url.origin === self.location.origin ? url.href : self.location.origin + "/";
  } catch {
    return self.location.origin + "/";
  }
}

self.addEventListener("push", event => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch { payload = {}; }
  const title = typeof payload.title === "string" && payload.title ? payload.title : "Novo aviso";
  const tag = typeof payload.tag === "string" && payload.tag ? payload.tag : "shopman-notification";
  event.waitUntil(self.registration.showNotification(title, {
    body: typeof payload.body === "string" ? payload.body : "",
    tag,
    renotify: payload.severity === "critical",
    data: { action_url: shopmanSafeActionUrl(payload.action_url) },
  }));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = shopmanSafeActionUrl(event.notification.data && event.notification.data.action_url);
  event.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(async windows => {
    if (new URL(target).origin !== self.location.origin) return clients.openWindow(target);
    const samePath = windows.find(client => {
      try { return new URL(client.url).pathname === new URL(target).pathname; } catch { return false; }
    });
    const candidate = samePath || windows[0];
    if (candidate) {
      if ("navigate" in candidate) await candidate.navigate(target);
      return candidate.focus();
    }
    return clients.openWindow(target);
  }));
});

self.addEventListener("pushsubscriptionchange", event => {
  event.waitUntil((async () => {
    const oldSubscription = event.oldSubscription;
    const oldEndpoint = oldSubscription && oldSubscription.endpoint;
    const options = oldSubscription && oldSubscription.options;
    if (!oldEndpoint || !options || !options.applicationServerKey) return;
    const response = await fetch(SHOPMAN_PUSH_API, { credentials: "include", headers: { accept: "application/json" } });
    if (!response.ok) return;
    const body = await response.json();
    const device = Array.isArray(body.devices) ? body.devices.find(item => item.endpoint === oldEndpoint) : null;
    if (!device) return;
    const subscription = event.newSubscription || await self.registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: options.applicationServerKey,
    });
    await fetch(SHOPMAN_PUSH_API, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({
        subscription: subscription.toJSON(),
        surface_ref: device.surface_ref,
        device_label: device.device_label,
        categories: device.categories,
      }),
    });
  })());
});
`;

export default defineEventHandler(event => {
  setResponseHeader(event, "content-type", "application/javascript; charset=utf-8");
  setResponseHeader(event, "cache-control", "no-cache, no-store, must-revalidate");
  return OPERATOR_PUSH_WORKER;
});
