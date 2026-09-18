import { describe, expect, it, vi } from "vitest";
import { OPERATOR_PUSH_WORKER } from "../runtime/server/push-worker";

function workerHarness() {
  const listeners = new Map<string, (event: any) => void>();
  const navigate = vi.fn().mockResolvedValue(undefined);
  const focus = vi.fn().mockResolvedValue(undefined);
  const openWindow = vi.fn().mockResolvedValue(undefined);
  const clients = {
    matchAll: vi.fn().mockResolvedValue([{ url: "https://central.example.test/", navigate, focus }]),
    openWindow,
  };
  const self = {
    location: { origin: "https://central.example.test" },
    registration: { showNotification: vi.fn().mockResolvedValue(undefined) },
    addEventListener: (name: string, listener: (event: any) => void) => listeners.set(name, listener),
  };
  Function("self", "clients", OPERATOR_PUSH_WORKER)(self, clients);
  return { listeners, navigate, focus, openWindow, self };
}

describe("operator push service worker", () => {
  it("mostra push, abre a action_url e reassina endpoints rotacionados", () => {
    expect(OPERATOR_PUSH_WORKER).toContain('addEventListener("push"');
    expect(OPERATOR_PUSH_WORKER).toContain('addEventListener("notificationclick"');
    expect(OPERATOR_PUSH_WORKER).toContain('clients.openWindow(target)');
    expect(OPERATOR_PUSH_WORKER).toContain('addEventListener("pushsubscriptionchange"');
    expect(OPERATOR_PUSH_WORKER).toContain('method: "POST"');
  });

  it("executa notificationclick na rota same-origin e foca a janela", async () => {
    const harness = workerHarness();
    let pending = Promise.resolve();
    harness.listeners.get("notificationclick")!({
      notification: { close: vi.fn(), data: { action_url: "/alerts/9" } },
      waitUntil: (value: Promise<void>) => { pending = value; },
    });
    await pending;
    expect(harness.navigate).toHaveBeenCalledWith("https://central.example.test/alerts/9");
    expect(harness.focus).toHaveBeenCalledOnce();
  });

  it("abre a surface canônica em vez de navegar cliente de outro origin", async () => {
    const harness = workerHarness();
    let pending = Promise.resolve();
    harness.listeners.get("notificationclick")!({
      notification: { close: vi.fn(), data: { action_url: "https://mkt.example.test/announcements/7" } },
      waitUntil: (value: Promise<void>) => { pending = value; },
    });
    await pending;
    expect(harness.openWindow).toHaveBeenCalledWith("https://mkt.example.test/announcements/7");
    expect(harness.navigate).not.toHaveBeenCalled();
  });

  it("mantém o transporte fora do cache e limita destinos ao mesmo origin", () => {
    expect(OPERATOR_PUSH_WORKER).toContain('credentials: "include"');
    expect(OPERATOR_PUSH_WORKER).toContain("url.origin === self.location.origin");
    expect(OPERATOR_PUSH_WORKER).not.toContain("caches.open");
  });
});
