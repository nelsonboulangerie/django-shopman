// O plugin da layer registra todo toque real no relógio do dispositivo — sem que
// nenhum app monte componente. Roda no runtime Nuxt de verdade (o kit é a raiz
// do projeto de teste, então o plugin `deviceActivity.client.ts` está carregado).
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRouter } from "#app";
import { DEVICE_ACTIVITY_COOKIE_NAME, DEVICE_ACTIVITY_THROTTLE_MS, parseDeviceActivity } from "../../app/utils/deviceActivity";

function clearClock() {
  document.cookie = `${DEVICE_ACTIVITY_COOKIE_NAME}=; Path=/; Max-Age=0`;
}

function deviceActivity(): number | null {
  return parseDeviceActivity(document.cookie, Date.now());
}

afterEach(() => {
  clearClock();
  vi.useRealTimers();
});

describe("plugin deviceActivity.client", () => {
  it.each(["pointerdown", "keydown", "wheel", "touchstart", "pointermove"])(
    "%s em qualquer app de operador marca o relógio do dispositivo",
    (event) => {
      clearClock();
      expect(deviceActivity()).toBeNull();
      window.dispatchEvent(new Event(event));
      expect(deviceActivity()).not.toBeNull();
    },
  );

  it("escuta na captura: stopPropagation de um componente não esconde o toque", () => {
    clearClock();
    const button = document.createElement("button");
    button.addEventListener("pointerdown", (event) => event.stopPropagation());
    document.body.appendChild(button);
    button.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    button.remove();
    expect(deviceActivity()).not.toBeNull();
  });

  it("rajada de pointermove escreve uma vez por janela de throttle", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-17T10:00:00Z"));
    clearClock();
    window.dispatchEvent(new Event("pointermove"));
    const first = deviceActivity();
    vi.setSystemTime(Date.now() + DEVICE_ACTIVITY_THROTTLE_MS - 1);
    for (let i = 0; i < 50; i++) window.dispatchEvent(new Event("pointermove"));
    expect(deviceActivity()).toBe(first);
    vi.setSystemTime(Date.now() + 1);
    window.dispatchEvent(new Event("pointermove"));
    expect(deviceActivity()).toBe(Date.now());
  });

  it("rota com `operatorActivity: false` (tela do cliente) não conta como operador presente", () => {
    clearClock();
    const meta = useRouter().currentRoute.value.meta as Record<string, unknown>;
    meta.operatorActivity = false;
    try {
      window.dispatchEvent(new Event("pointerdown"));
      expect(deviceActivity()).toBeNull();
    } finally {
      delete meta.operatorActivity;
    }
  });
});
