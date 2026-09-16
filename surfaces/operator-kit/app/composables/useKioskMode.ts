import { onBeforeUnmount, onMounted, readonly, ref, shallowRef } from "vue";

interface FullscreenDocumentCapability {
  fullscreenElement: Element | null;
  exitFullscreen?: () => Promise<void>;
}

interface FullscreenElementCapability {
  requestFullscreen?: () => Promise<void>;
}

interface KioskModeOptions {
  enabled?: boolean;
  idleMs?: number;
  onIdle?: () => void | Promise<void>;
}

const ACTIVITY_EVENTS = ["pointerdown", "keydown", "touchstart"] as const;

/** Progressive fullscreen + idle signal shared by wall displays. */
export function useKioskMode(options: KioskModeOptions = {}) {
  const enabled = options.enabled !== false;
  const idleMs = Math.max(1_000, options.idleMs ?? 60_000);
  const supported = ref(false);
  const isFullscreen = ref(false);
  const isIdle = ref(false);
  const lastError = shallowRef<unknown>(null);
  let idleTimer: ReturnType<typeof setTimeout> | null = null;

  function fullscreenDocument() {
    return document as unknown as FullscreenDocumentCapability;
  }

  function syncFullscreen() {
    if (!import.meta.client) return;
    isFullscreen.value = Boolean(fullscreenDocument().fullscreenElement);
  }

  function clearIdleTimer() {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = null;
  }

  function scheduleIdle() {
    if (!enabled || !import.meta.client) return;
    clearIdleTimer();
    isIdle.value = false;
    idleTimer = setTimeout(() => {
      isIdle.value = true;
      try {
        void Promise.resolve(options.onIdle?.()).catch((error) => {
          lastError.value = error;
        });
      } catch (error) {
        lastError.value = error;
      }
    }, idleMs);
  }

  async function enter(element?: HTMLElement | null): Promise<boolean> {
    if (!enabled || !import.meta.client) return false;
    const target = (element || document.documentElement) as unknown as FullscreenElementCapability;
    supported.value = typeof target.requestFullscreen === "function";
    if (!target.requestFullscreen) return false;
    try {
      await target.requestFullscreen();
      syncFullscreen();
      lastError.value = null;
      return true;
    } catch (error) {
      lastError.value = error;
      return false;
    }
  }

  async function exit(): Promise<boolean> {
    if (!import.meta.client) return false;
    const current = fullscreenDocument();
    if (!current.exitFullscreen || !current.fullscreenElement) return false;
    try {
      await current.exitFullscreen();
      syncFullscreen();
      lastError.value = null;
      return true;
    } catch (error) {
      lastError.value = error;
      return false;
    }
  }

  onMounted(() => {
    const target = document.documentElement as unknown as FullscreenElementCapability;
    supported.value = typeof target.requestFullscreen === "function";
    syncFullscreen();
    if (!enabled) return;
    document.addEventListener("fullscreenchange", syncFullscreen);
    for (const event of ACTIVITY_EVENTS) window.addEventListener(event, scheduleIdle, { passive: true });
    scheduleIdle();
  });

  onBeforeUnmount(() => {
    clearIdleTimer();
    if (!import.meta.client) return;
    document.removeEventListener("fullscreenchange", syncFullscreen);
    for (const event of ACTIVITY_EVENTS) window.removeEventListener(event, scheduleIdle);
  });

  return {
    supported: readonly(supported),
    isFullscreen: readonly(isFullscreen),
    isIdle: readonly(isIdle),
    lastError: readonly(lastError),
    enter,
    exit,
    markActive: scheduleIdle,
  };
}
