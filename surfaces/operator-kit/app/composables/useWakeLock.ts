import { onBeforeUnmount, onMounted, readonly, ref, shallowRef } from "vue";

interface ScreenWakeLockSentinel extends EventTarget {
  readonly released: boolean;
  release(): Promise<void>;
}

interface NavigatorWakeLockCapability {
  wakeLock?: {
    request(type: "screen"): Promise<ScreenWakeLockSentinel>;
  };
}

/**
 * Mantém uma surface operacional acordada sem transformar ausência de API em erro.
 *
 * Wake Lock é uma melhoria progressiva: Safari antigo, política do aparelho, aba
 * oculta e recusa do navegador resultam em `false`, nunca em exceção para a tela.
 * Ao voltar ao primeiro plano, o lock é pedido novamente porque o navegador libera
 * automaticamente o sentinel quando o documento deixa de estar visível.
 */
export function useWakeLock(options: { enabled?: boolean } = {}) {
  const enabled = options.enabled !== false;
  const supported = ref(false);
  const active = ref(false);
  const lastError = shallowRef<unknown>(null);
  let sentinel: ScreenWakeLockSentinel | null = null;

  function wakeLockManager() {
    if (!import.meta.client) return null;
    const manager = (navigator as unknown as NavigatorWakeLockCapability).wakeLock;
    supported.value = Boolean(manager?.request);
    return manager || null;
  }

  function forgetSentinel(current: ScreenWakeLockSentinel) {
    if (sentinel !== current) return;
    sentinel = null;
    active.value = false;
  }

  async function request(): Promise<boolean> {
    if (!enabled || !import.meta.client || document.visibilityState !== "visible") return false;
    if (sentinel && !sentinel.released) return true;

    const manager = wakeLockManager();
    if (!manager) return false;

    try {
      const current = await manager.request("screen");
      sentinel = current;
      active.value = !current.released;
      lastError.value = null;
      current.addEventListener("release", () => forgetSentinel(current), { once: true });
      return active.value;
    } catch (error) {
      sentinel = null;
      active.value = false;
      lastError.value = error;
      return false;
    }
  }

  async function release(): Promise<void> {
    const current = sentinel;
    sentinel = null;
    active.value = false;
    if (!current || current.released) return;
    try {
      await current.release();
    } catch (error) {
      lastError.value = error;
    }
  }

  function onVisibilityChange() {
    if (document.visibilityState === "visible") void request();
  }

  onMounted(() => {
    wakeLockManager();
    if (!enabled) return;
    document.addEventListener("visibilitychange", onVisibilityChange);
    void request();
  });

  onBeforeUnmount(() => {
    if (import.meta.client) document.removeEventListener("visibilitychange", onVisibilityChange);
    void release();
  });

  return {
    active: readonly(active),
    supported: readonly(supported),
    lastError: readonly(lastError),
    request,
    release,
  };
}
