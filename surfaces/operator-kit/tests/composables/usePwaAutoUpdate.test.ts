import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import { bindPwaUpdateRegistration } from "../../app/composables/usePwaUpdate";
import { usePwaAutoUpdate } from "../../app/composables/usePwaAutoUpdate";
import { PWA_UPDATE_CHECK_MS, PWA_UPDATE_IDLE_MS } from "../../app/presentation/pwaRuntime";

function fakeWorker() {
  const needRefresh = ref(false);
  const updateServiceWorker = vi.fn().mockResolvedValue(undefined);
  const checkForUpdate = vi.fn().mockResolvedValue(true);
  bindPwaUpdateRegistration({ needRefresh, updateServiceWorker, checkForUpdate });
  return { needRefresh, updateServiceWorker, checkForUpdate };
}

async function mountAuto(options: Partial<Parameters<typeof usePwaAutoUpdate>[0]> = {}) {
  let state!: ReturnType<typeof usePwaAutoUpdate>;
  const wrapper = await mountSuspended(defineComponent({
    setup() {
      state = usePwaAutoUpdate({
        app: "pos",
        appVersion: "velha1",
        allowedPaths: () => ["/"],
        path: () => "/",
        report: () => Promise.resolve(null),
        ...options,
      });
      return () => h("span");
    },
  }));
  await nextTick();
  return { state, wrapper };
}

/** Deixa o timer de ociosidade vencer e as promessas do `watch` assentarem. */
async function goIdle() {
  await vi.advanceTimersByTimeAsync(PWA_UPDATE_IDLE_MS);
  await nextTick();
  await nextTick();
}

beforeEach(() => {
  // `shouldAdvanceTime`: o `mountSuspended` do @nuxt/test-utils espera por timer real
  // para resolver o Suspense — com o relógio inteiramente parado o mount trava.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("localStorage", {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  } as unknown as Storage);
});

afterEach(() => {
  bindPwaUpdateRegistration(null);
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("sonda de versão nova", () => {
  it("pergunta ao servidor no boot e a cada 30 min", async () => {
    const worker = fakeWorker();
    const { wrapper } = await mountAuto();

    expect(worker.checkForUpdate).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(PWA_UPDATE_CHECK_MS);
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(PWA_UPDATE_CHECK_MS);
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(3);

    wrapper.unmount();
  });

  it("pergunta ao voltar do segundo plano e ao ganhar foco", async () => {
    const worker = fakeWorker();
    const { wrapper } = await mountAuto();
    worker.checkForUpdate.mockClear();

    // O piso entre sondas separa a rajada de gatilhos que chega junto ao acordar.
    await vi.advanceTimersByTimeAsync(90_000);
    document.dispatchEvent(new Event("visibilitychange"));
    await nextTick();
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(1);

    window.dispatchEvent(new Event("focus"));
    await nextTick();
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(90_000);
    window.dispatchEvent(new Event("focus"));
    await nextTick();
    expect(worker.checkForUpdate).toHaveBeenCalledTimes(2);

    wrapper.unmount();
  });

  it("para de perguntar quando a superfície é desmontada", async () => {
    const worker = fakeWorker();
    const { wrapper } = await mountAuto();
    wrapper.unmount();
    worker.checkForUpdate.mockClear();

    await vi.advanceTimersByTimeAsync(PWA_UPDATE_CHECK_MS * 3);
    window.dispatchEvent(new Event("focus"));
    expect(worker.checkForUpdate).not.toHaveBeenCalled();
  });
});

describe("aplicação automática", () => {
  it("entra sozinha quando a superfície fica ociosa na rota liberada", async () => {
    const worker = fakeWorker();
    const { state, wrapper } = await mountAuto();
    worker.needRefresh.value = true;
    await nextTick();

    expect(worker.updateServiceWorker).not.toHaveBeenCalled();
    await goIdle();

    expect(worker.updateServiceWorker).toHaveBeenCalledWith(true);
    expect(state.applying.value).toBe(true);
    wrapper.unmount();
  });

  it("uma razão de espera do PDV barra a troca até a venda terminar", async () => {
    const worker = fakeWorker();
    const holds = ref<string[]>(["tab_open"]);
    const { state, wrapper } = await mountAuto({ holds: () => holds.value });
    worker.needRefresh.value = true;
    await nextTick();

    await goIdle();
    expect(worker.updateServiceWorker).not.toHaveBeenCalled();
    expect(state.blocker.value).toBe("tab_open");

    // A comanda fecha e ninguém toca em nada: a observação fecha essa janela.
    holds.value = [];
    await nextTick();
    await nextTick();
    expect(worker.updateServiceWorker).toHaveBeenCalledWith(true);
    wrapper.unmount();
  });

  it("toque humano adia: o operador na tela não é interrompido", async () => {
    const worker = fakeWorker();
    const { state, wrapper } = await mountAuto();
    worker.needRefresh.value = true;
    await nextTick();

    for (let i = 0; i < 4; i += 1) {
      await vi.advanceTimersByTimeAsync(PWA_UPDATE_IDLE_MS - 1_000);
      window.dispatchEvent(new Event("pointerdown"));
      await nextTick();
    }
    expect(worker.updateServiceWorker).not.toHaveBeenCalled();
    expect(state.blocker.value).toBe("busy");

    await goIdle();
    expect(worker.updateServiceWorker).toHaveBeenCalledOnce();
    wrapper.unmount();
  });

  it("rota fora da lista nunca aplica sozinha, por mais parada que esteja", async () => {
    const worker = fakeWorker();
    const { state, wrapper } = await mountAuto({ path: () => "/session/closing" });
    worker.needRefresh.value = true;
    await nextTick();

    await goIdle();
    expect(worker.updateServiceWorker).not.toHaveBeenCalled();
    expect(state.blocker.value).toBe("unsafe_route");
    wrapper.unmount();
  });

  it("app sem rota liberada fica só no aviso ao operador", async () => {
    const worker = fakeWorker();
    const { wrapper } = await mountAuto({ allowedPaths: () => [] });
    worker.needRefresh.value = true;
    await nextTick();

    await goIdle();
    expect(worker.updateServiceWorker).not.toHaveBeenCalled();
    // …mas segue sondando: é assim que o aviso chega a aparecer.
    expect(worker.checkForUpdate).toHaveBeenCalled();
    wrapper.unmount();
  });

  it("não dispara duas trocas enquanto a primeira está em curso", async () => {
    const worker = fakeWorker();
    worker.updateServiceWorker.mockImplementation(() => new Promise(() => {}));
    const { wrapper } = await mountAuto();
    worker.needRefresh.value = true;
    await nextTick();

    await goIdle();
    await goIdle();
    expect(worker.updateServiceWorker).toHaveBeenCalledOnce();
    wrapper.unmount();
  });
});

describe("telemetria", () => {
  it("relata a troca anterior no boot, com as duas versões", async () => {
    fakeWorker();
    const report = vi.fn().mockResolvedValue({
      app: "pos",
      trigger: "idle",
      from_version: "velha1",
      to_version: "nova22",
    });
    const { state, wrapper } = await mountAuto({ appVersion: "nova22", report });
    await nextTick();

    expect(report).toHaveBeenCalledWith("nova22");
    expect(state.lastReport.value).toMatchObject({ from_version: "velha1", to_version: "nova22" });
    wrapper.unmount();
  });

  it("grava a marca ANTES do reload — depois dele não há quem conte", async () => {
    const worker = fakeWorker();
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { getItem: () => null, setItem, removeItem: () => {} } as unknown as Storage);
    const { wrapper } = await mountAuto({ appVersion: "velha1" });
    worker.needRefresh.value = true;
    await nextTick();

    await goIdle();

    expect(setItem).toHaveBeenCalledWith(
      "shopman:operator:pwa-update",
      JSON.stringify({ app: "pos", trigger: "idle", from_version: "velha1" }),
    );
    expect(setItem.mock.invocationCallOrder[0]).toBeLessThan(
      worker.updateServiceWorker.mock.invocationCallOrder[0],
    );
    wrapper.unmount();
  });
});
