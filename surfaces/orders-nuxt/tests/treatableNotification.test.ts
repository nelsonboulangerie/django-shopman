import { describe, expect, it, vi } from "vitest";
import { showTreatableOrderNotification } from "../app/utils/treatableNotification";

function registration() {
  return { showNotification: vi.fn().mockResolvedValue(undefined) } as unknown as ServiceWorkerRegistration;
}

function serviceWorker(current: ServiceWorkerRegistration | null, ready = Promise.resolve(registration())) {
  return {
    getRegistration: vi.fn().mockResolvedValue(current),
    ready,
  } as unknown as Pick<ServiceWorkerContainer, "getRegistration" | "ready">;
}

describe("notificação local de pedido tratável", () => {
  it("usa o service worker com a mesma copy, tag e rota do Gestor", async () => {
    const current = registration();
    const ok = await showTreatableOrderNotification("WEB-7", {
      permission: "granted",
      serviceWorker: serviceWorker(current),
      actionUrl: "/?view=board",
    });

    expect(ok).toBe(true);
    expect(current.showNotification).toHaveBeenCalledWith("Pedido para tratar WEB-7", {
      body: "Há um pedido que já pode ser tratado no quadro.",
      tag: "gestor-treatable-order",
      data: { action_url: "/?view=board" },
    });
  });

  it("espera de forma limitada o registro que ainda está ficando pronto", async () => {
    const ready = registration();
    const ok = await showTreatableOrderNotification("PRE-1", {
      permission: "granted",
      serviceWorker: serviceWorker(null, Promise.resolve(ready)),
      actionUrl: "/",
      registrationWaitMs: 10,
    });
    expect(ok).toBe(true);
    expect(ready.showNotification).toHaveBeenCalledOnce();
  });

  it("não espera ready indefinidamente", async () => {
    vi.useFakeTimers();
    try {
      const never = new Promise<ServiceWorkerRegistration>(() => {});
      const pending = showTreatableOrderNotification("PRE-2", {
        permission: "granted",
        serviceWorker: serviceWorker(null, never),
        actionUrl: "/",
        registrationWaitMs: 25,
      });
      await vi.advanceTimersByTimeAsync(25);
      await expect(pending).resolves.toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it.each(["default", "denied"] as const)("permissão %s não toca no registro", async (permission) => {
    const worker = serviceWorker(registration());
    expect(await showTreatableOrderNotification("WEB-8", {
      permission,
      serviceWorker: worker,
      actionUrl: "/",
    })).toBe(false);
    expect(worker.getRegistration).not.toHaveBeenCalled();
  });

  it("sem worker ou com falha no registro degrada sem rejeitar", async () => {
    await expect(showTreatableOrderNotification("WEB-9", {
      permission: "granted",
      actionUrl: "/",
    })).resolves.toBe(false);
    const broken = {
      getRegistration: vi.fn().mockRejectedValue(new Error("worker unavailable")),
      ready: Promise.resolve(registration()),
    } as unknown as Pick<ServiceWorkerContainer, "getRegistration" | "ready">;
    await expect(showTreatableOrderNotification("WEB-9", {
      permission: "granted",
      serviceWorker: broken,
      actionUrl: "/",
    })).resolves.toBe(false);

    const neverReady = serviceWorker(null, Promise.reject(new Error("not ready")));
    await expect(showTreatableOrderNotification("WEB-10", {
      permission: "granted",
      serviceWorker: neverReady,
      actionUrl: "/",
    })).resolves.toBe(false);
  });
});
