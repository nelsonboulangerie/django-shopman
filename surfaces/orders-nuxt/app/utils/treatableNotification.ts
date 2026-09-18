const DEFAULT_REGISTRATION_WAIT_MS = 1_000;

export interface TreatableNotificationRuntime {
  permission: NotificationPermission;
  serviceWorker?: Pick<ServiceWorkerContainer, "getRegistration" | "ready">;
  actionUrl: string;
  registrationWaitMs?: number;
}

async function availableRegistration(
  serviceWorker: NonNullable<TreatableNotificationRuntime["serviceWorker"]>,
  waitMs: number,
): Promise<ServiceWorkerRegistration | null> {
  const current = await serviceWorker.getRegistration();
  if (current) return current;

  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      Promise.resolve(serviceWorker.ready).catch(() => null),
      new Promise<null>((resolve) => {
        timeout = setTimeout(resolve, Math.max(0, waitMs), null);
      }),
    ]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

/**
 * Mostra o alerta local pelo service worker, sem pedir permissão e sem bloquear
 * som/título do quadro. O Web Push remoto é uma perna independente.
 */
export async function showTreatableOrderNotification(
  ref_: string,
  runtime: TreatableNotificationRuntime,
): Promise<boolean> {
  if (runtime.permission !== "granted" || !runtime.serviceWorker) return false;
  try {
    const registration = await availableRegistration(
      runtime.serviceWorker,
      runtime.registrationWaitMs ?? DEFAULT_REGISTRATION_WAIT_MS,
    );
    if (!registration) return false;
    await registration.showNotification(`Pedido para tratar${ref_ ? ` ${ref_}` : ""}`, {
      body: "Há um pedido que já pode ser tratado no quadro.",
      tag: "gestor-treatable-order",
      data: { action_url: runtime.actionUrl || "/" },
    });
    return true;
  } catch {
    // Notificação local é enhancement: SSE, som e título continuam canônicos.
    return false;
  }
}
