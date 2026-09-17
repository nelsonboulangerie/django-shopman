import { computed, onBeforeUnmount, onMounted, readonly, shallowRef } from "vue";
import {
  ORIENTATION_LOCK_COPY,
  ORIENTATION_LOCK_STORAGE_KEY,
  orientationFailureCopy,
  orientationFamily,
  orientationLockedCopy,
  orientationLockFailure,
  parseStoredOrientation,
} from "../presentation/orientationLock";
import type { OrientationFamily, OrientationLockStatus } from "../presentation/orientationLock";

// `lock`/`unlock` saíram do lib.dom do TypeScript (a API é parcial entre navegadores);
// a forma mínima que o kit usa fica declarada aqui, como no useWakeLock.
interface ScreenOrientationCapability {
  readonly type?: string;
  lock?: (orientation: OrientationFamily) => Promise<void>;
  unlock?: () => void;
}

interface NavigatorWithStandalone extends Navigator {
  standalone?: boolean;
}

export interface OrientationLockResult {
  ok: boolean;
  status: OrientationLockStatus;
  message: string;
}

/**
 * Trava de giro da tela por aparelho — o manifesto deixa o app girar (`orientation:
 * "any"`) e o operador decide, no rail, travar na orientação em que o tablet está.
 *
 * A Screen Orientation API só trava de verdade em app instalado (display standalone/
 * fullscreen) ou em tela cheia, e na prática só Android/ChromeOS deixam. iPhone/iPad e
 * Windows recusam. Por isso a trava nunca é presumida: `lock()` tenta, e a recusa vira
 * estado + cópia curta para o operador ("use o bloqueio de rotação do sistema") — o
 * rail nunca mostra "travado" sem o navegador ter confirmado.
 *
 * A preferência mora no `localStorage` do aparelho (a trava é do tablet, não do
 * operador) e é reaplicada no boot do app instalado por quem pede `{ restore: true }`
 * (o `OperatorPwaRuntime`, uma vez por app). O navegador solta a trava ao recarregar e
 * ao sair de tela cheia; por isso o restore também escuta `visibilitychange` e
 * `fullscreenchange`.
 */
export function useOrientationLock(options: { restore?: boolean } = {}) {
  // Verdade compartilhada no app: o item do rail e o restore do runtime enxergam o
  // mesmo estado.
  const locked = useState<OrientationFamily | null>("operator-orientation-lock", () => null);
  const status = useState<OrientationLockStatus>("operator-orientation-lock-status", () => "unlocked");
  const available = useState<boolean>("operator-orientation-lock-available", () => false);
  const lastError = shallowRef<unknown>(null);

  function orientationApi(): ScreenOrientationCapability | null {
    if (!import.meta.client || typeof screen === "undefined") return null;
    return (screen as unknown as { orientation?: ScreenOrientationCapability }).orientation || null;
  }

  function isIos(): boolean {
    const ua = navigator.userAgent;
    return /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function isInstalled(): boolean {
    const displayMode = ["standalone", "fullscreen", "minimal-ui"]
      .some((mode) => window.matchMedia?.(`(display-mode: ${mode})`).matches);
    return displayMode
      || Boolean((navigator as NavigatorWithStandalone).standalone)
      || Boolean(document.fullscreenElement);
  }

  /** Só aparelho de toque gira: um PC sem tela sensível não ganha o controle. */
  function detectAvailability() {
    available.value = Boolean(orientationApi()) && (navigator.maxTouchPoints || 0) > 0;
  }

  function readPreference(): OrientationFamily | null {
    try {
      return parseStoredOrientation(localStorage.getItem(ORIENTATION_LOCK_STORAGE_KEY));
    } catch {
      return null;
    }
  }

  function writePreference(family: OrientationFamily | null) {
    try {
      if (family) localStorage.setItem(ORIENTATION_LOCK_STORAGE_KEY, family);
      else localStorage.removeItem(ORIENTATION_LOCK_STORAGE_KEY);
    } catch {
      // Storage bloqueado: a trava vale nesta sessão, só não volta sozinha no boot.
    }
  }

  function failure(error: unknown): OrientationLockResult {
    lastError.value = error;
    locked.value = null;
    const reason = orientationLockFailure({ installed: isInstalled(), ios: isIos() });
    status.value = reason;
    return { ok: false, status: reason, message: orientationFailureCopy(reason) };
  }

  async function apply(family: OrientationFamily): Promise<OrientationLockResult> {
    const api = orientationApi();
    if (!api || typeof api.lock !== "function") return failure(null);
    try {
      await api.lock(family);
      locked.value = family;
      status.value = "locked";
      lastError.value = null;
      return { ok: true, status: "locked", message: orientationLockedCopy(family) };
    } catch (error) {
      return failure(error);
    }
  }

  /** Trava na orientação em que o aparelho está agora e guarda a escolha. */
  async function lock(): Promise<OrientationLockResult> {
    if (!import.meta.client) return { ok: false, status: status.value, message: "" };
    const family = orientationFamily(orientationApi()?.type)
      || (window.innerHeight > window.innerWidth ? "portrait" : "landscape");
    const result = await apply(family);
    // Só a trava CONFIRMADA vira preferência — nada de reabrir "travado" um aparelho
    // que nunca deixou travar.
    if (result.ok) writePreference(family);
    return result;
  }

  function unlock(): OrientationLockResult {
    try {
      orientationApi()?.unlock?.();
    } catch (error) {
      lastError.value = error;
    }
    writePreference(null);
    locked.value = null;
    status.value = "unlocked";
    return { ok: true, status: "unlocked", message: ORIENTATION_LOCK_COPY.unlocked };
  }

  function toggle(): Promise<OrientationLockResult> {
    return locked.value ? Promise.resolve(unlock()) : lock();
  }

  /**
   * Reaplica a preferência do aparelho — calado: no boot ninguém pediu nada, então a
   * recusa não vira aviso (e a preferência fica para a próxima abertura instalada).
   */
  async function restore(): Promise<boolean> {
    if (!import.meta.client) return false;
    const family = readPreference();
    if (!family || !isInstalled()) return false;
    const result = await apply(family);
    if (!result.ok) status.value = "unlocked";
    return result.ok;
  }

  function onVisibilityChange() {
    if (document.visibilityState === "visible") void restore();
  }

  function onFullscreenChange() {
    void restore();
  }

  onMounted(() => {
    detectAvailability();
    if (!options.restore) return;
    document.addEventListener("visibilitychange", onVisibilityChange);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    void restore();
  });

  onBeforeUnmount(() => {
    if (!options.restore || !import.meta.client) return;
    document.removeEventListener("visibilitychange", onVisibilityChange);
    document.removeEventListener("fullscreenchange", onFullscreenChange);
  });

  return {
    available: readonly(available),
    locked: readonly(locked),
    status: readonly(status),
    isLocked: computed(() => locked.value !== null),
    lastError: readonly(lastError),
    lock,
    unlock,
    toggle,
    restore,
  };
}
