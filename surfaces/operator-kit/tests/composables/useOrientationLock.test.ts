// Trava de giro no dispositivo real é Android/ChromeOS instalado; aqui a Screen Orientation
// API é substituída por um dublê que resolve (Android) ou rejeita (iOS/Windows) — o que
// se prova é que o estado só diz "travado" quando o navegador confirmou, que a recusa
// vira cópia para o operador, e que a escolha volta no boot do app instalado.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { useOrientationLock } from "../../app/composables/useOrientationLock";
import { ORIENTATION_LOCK_COPY, ORIENTATION_LOCK_STORAGE_KEY } from "../../app/presentation/orientationLock";

const USER_AGENT = navigator.userAgent;

function stubOrientation(value: unknown) {
  Object.defineProperty(screen, "orientation", { configurable: true, value });
}

function stubDevice({ touch = 5, installed = false, userAgent = "Mozilla/5.0 (Linux; Android 14; Tab)" } = {}) {
  Object.defineProperty(navigator, "maxTouchPoints", { configurable: true, value: touch });
  Object.defineProperty(navigator, "userAgent", { configurable: true, value: userAgent });
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: installed && query === "(display-mode: standalone)",
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
}

async function mountOrientation(options: Parameters<typeof useOrientationLock>[0] = {}) {
  let state!: ReturnType<typeof useOrientationLock>;
  const wrapper = await mountSuspended(defineComponent({
    setup() {
      state = useOrientationLock(options);
      return () => h("span");
    },
  }));
  await nextTick();
  return { state, wrapper };
}

beforeEach(() => {
  localStorage.clear();
  useState("operator-orientation-lock").value = null;
  useState("operator-orientation-lock-status").value = "unlocked";
  useState("operator-orientation-lock-available").value = false;
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "userAgent", { configurable: true, value: USER_AGENT });
});

describe("useOrientationLock", () => {
  it("PC sem toque não ganha o controle; tablet com a API ganha", async () => {
    stubOrientation({ type: "landscape-primary", lock: vi.fn(), unlock: vi.fn() });
    stubDevice({ touch: 0 });
    const desktop = await mountOrientation();
    expect(desktop.state.available.value).toBe(false);
    desktop.wrapper.unmount();

    stubDevice({ touch: 5 });
    const tablet = await mountOrientation();
    expect(tablet.state.available.value).toBe(true);
    tablet.wrapper.unmount();
  });

  it("Android instalado: trava na orientação ATUAL, guarda a escolha e libera", async () => {
    const lock = vi.fn().mockResolvedValue(undefined);
    const unlock = vi.fn();
    stubOrientation({ type: "portrait-secondary", lock, unlock });
    stubDevice({ installed: true });
    const { state, wrapper } = await mountOrientation();

    const locked = await state.lock();
    expect(lock).toHaveBeenCalledWith("portrait");
    expect(locked).toEqual({ ok: true, status: "locked", message: "Giro travado em retrato." });
    expect(state.locked.value).toBe("portrait");
    expect(localStorage.getItem(ORIENTATION_LOCK_STORAGE_KEY)).toBe("portrait");

    const released = await state.toggle();
    expect(unlock).toHaveBeenCalledOnce();
    expect(released.message).toBe(ORIENTATION_LOCK_COPY.unlocked);
    expect(state.isLocked.value).toBe(false);
    expect(localStorage.getItem(ORIENTATION_LOCK_STORAGE_KEY)).toBeNull();
    wrapper.unmount();
  });

  it("dispositivo instalado que recusa (Windows): diz ao operador e NÃO finge que travou", async () => {
    stubOrientation({
      type: "landscape-primary",
      lock: vi.fn().mockRejectedValue(new DOMException("not supported", "NotSupportedError")),
      unlock: vi.fn(),
    });
    stubDevice({ installed: true, userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" });
    const { state, wrapper } = await mountOrientation();

    const result = await state.toggle();
    expect(result).toEqual({ ok: false, status: "unsupported", message: ORIENTATION_LOCK_COPY.unsupported });
    expect(state.isLocked.value).toBe(false);
    expect(state.lastError.value).toBeInstanceOf(DOMException);
    expect(localStorage.getItem(ORIENTATION_LOCK_STORAGE_KEY)).toBeNull();
    wrapper.unmount();
  });

  it("aba comum do navegador: a recusa manda abrir o app instalado", async () => {
    stubOrientation({
      type: "landscape-primary",
      lock: vi.fn().mockRejectedValue(new DOMException("needs fullscreen", "SecurityError")),
    });
    stubDevice({ installed: false });
    const { state, wrapper } = await mountOrientation();

    const result = await state.lock();
    expect(result.status).toBe("needs-install");
    expect(result.message).toBe(ORIENTATION_LOCK_COPY.needsInstall);
    wrapper.unmount();
  });

  it("iPad sem lock(): o dispositivo não deixa — nada de mandar instalar", async () => {
    stubOrientation({ type: "landscape-primary" });
    stubDevice({ installed: false, userAgent: "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)" });
    const { state, wrapper } = await mountOrientation();

    const result = await state.lock();
    expect(result).toEqual({ ok: false, status: "unsupported", message: ORIENTATION_LOCK_COPY.unsupported });
    wrapper.unmount();
  });

  it("boot do app instalado reaplica a escolha guardada, e de novo ao voltar do segundo plano", async () => {
    localStorage.setItem(ORIENTATION_LOCK_STORAGE_KEY, "landscape");
    const lock = vi.fn().mockResolvedValue(undefined);
    stubOrientation({ type: "portrait-primary", lock, unlock: vi.fn() });
    stubDevice({ installed: true });
    const { state, wrapper } = await mountOrientation({ restore: true });

    await vi.waitFor(() => expect(lock).toHaveBeenCalledWith("landscape"));
    expect(state.locked.value).toBe("landscape");

    document.dispatchEvent(new Event("visibilitychange"));
    await vi.waitFor(() => expect(lock).toHaveBeenCalledTimes(2));
    wrapper.unmount();
  });

  it("boot fora do app instalado não tenta travar; recusa no boot fica calada e guarda a escolha", async () => {
    localStorage.setItem(ORIENTATION_LOCK_STORAGE_KEY, "portrait");
    const lock = vi.fn().mockRejectedValue(new DOMException("nope", "NotSupportedError"));
    stubOrientation({ type: "landscape-primary", lock });

    stubDevice({ installed: false });
    const tab = await mountOrientation({ restore: true });
    await nextTick();
    expect(lock).not.toHaveBeenCalled();
    tab.wrapper.unmount();

    stubDevice({ installed: true });
    const installed = await mountOrientation({ restore: true });
    await vi.waitFor(() => expect(lock).toHaveBeenCalledOnce());
    await nextTick();
    expect(installed.state.status.value).toBe("unlocked");
    expect(localStorage.getItem(ORIENTATION_LOCK_STORAGE_KEY)).toBe("portrait");
    installed.wrapper.unmount();
  });

  it("storage bloqueado não quebra a trava da sessão", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    stubOrientation({ type: "landscape-primary", lock: vi.fn().mockResolvedValue(undefined), unlock: vi.fn() });
    stubDevice({ installed: true });
    const { state, wrapper } = await mountOrientation();

    await expect(state.lock()).resolves.toMatchObject({ ok: true, status: "locked" });
    expect(state.locked.value).toBe("landscape");
    wrapper.unmount();
  });
});
