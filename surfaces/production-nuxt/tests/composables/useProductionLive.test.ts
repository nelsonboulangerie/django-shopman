// WP-F15 · Tempo real honesto: toda tela de lote ouve o canal da Produção, o evento
// refaz o GET canônico, e o poll fica de reserva.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import {
  PRODUCTION_LIVE_RESERVE_POLL_MS,
  useProductionLive,
} from "~/composables/useProductionLive";
import { useQcKiosk } from "~/composables/useQcKiosk";
import { useProductionKds } from "~/composables/useProductionKds";
import { useMiseEnPlace, usePrepMarks } from "~/composables/useMiseEnPlace";
import { useProductionForecast } from "~/composables/useProductionForecast";

const env = installNuxtGlobals();

/** EventSource de mentira: `failForGood` é a reconexão que recebeu 502 (CLOSED). */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, Array<() => void>>();
  close = vi.fn(() => {
    this.readyState = 2;
  });
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(name: string, handler: () => void) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), handler]);
  }
  emit(name: string) {
    for (const handler of this.listeners.get(name) ?? []) handler();
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  failForGood() {
    this.readyState = 2;
    this.onerror?.();
  }
}

/** Monta os composables com lifecycle e browser mínimos, e devolve o desmontar. */
async function withMountedBrowser<T>(build: () => T): Promise<{ value: T; unmount: () => void }> {
  const mounts: Array<() => void> = [];
  const unmounts: Array<() => void> = [];
  FakeEventSource.instances = [];
  vi.stubGlobal("onMounted", (callback: () => void) => {
    mounts.push(callback);
  });
  vi.stubGlobal("onBeforeUnmount", (callback: () => void) => {
    unmounts.push(callback);
  });
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("ssePath", (await import("../../../operator-kit/app/utils/ssePath")).ssePath);
  const value = build();
  mounts.forEach((callback) => callback());
  return { value, unmount: () => unmounts.forEach((callback) => callback()) };
}

/** A cadência que a tela entregou ao poll (a função que o `useAdaptivePoll` relê). */
function pollInterval(call = 0): () => number {
  return env.adaptivePoll.mock.calls[call]?.[1] as () => number;
}

describe("useProductionLive — o canal da Produção", () => {
  beforeEach(() => {
    env.reset();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.stubGlobal("onMounted", () => {});
    vi.stubGlobal("onBeforeUnmount", () => {});
  });

  it("ouve backstage-production e refaz o GET canônico a cada lote que muda", async () => {
    const refresh = vi.fn();
    const { value, unmount } = await withMountedBrowser(() =>
      useProductionLive(refresh, () => 30_000),
    );
    try {
      const source = FakeEventSource.instances[0]!;
      expect(source.url).toBe("/sse/production");
      expect(source.listeners.has("backstage-production-update")).toBe(true);
      expect(value.realtime.value).toBe("connecting");
      source.open();
      expect(value.realtime.value).toBe("live");
      source.emit("backstage-production-update");
      await vi.advanceTimersByTimeAsync(0);
      expect(refresh).toHaveBeenCalledTimes(1);
    } finally {
      unmount();
    }
  });

  it("o poll é reserva: 60 s com o canal aberto, a cadência da tela sem ele", async () => {
    const { value, unmount } = await withMountedBrowser(() =>
      useProductionLive(vi.fn(), () => 10_000),
    );
    try {
      const interval = pollInterval();
      // Conectando ainda não é ao vivo: a tela segue na cadência própria.
      expect(interval()).toBe(10_000);
      FakeEventSource.instances[0]!.open();
      expect(interval()).toBe(PRODUCTION_LIVE_RESERVE_POLL_MS);
      FakeEventSource.instances[0]!.failForGood();
      expect(value.realtime.value).toBe("polling");
      expect(interval()).toBe(10_000);
    } finally {
      unmount();
    }
  });

  it("duas leituras na mesma tela dividem UMA conexão, e cada uma relê a sua", async () => {
    const list = vi.fn();
    const marks = vi.fn();
    const { unmount } = await withMountedBrowser(() => {
      useProductionLive(list, () => 60_000);
      useProductionLive(marks, () => 60_000);
    });
    try {
      expect(FakeEventSource.instances).toHaveLength(1);
      const source = FakeEventSource.instances[0]!;
      source.open();
      source.emit("backstage-production-update");
      await vi.advanceTimersByTimeAsync(0);
      expect(list).toHaveBeenCalledTimes(1);
      expect(marks).toHaveBeenCalledTimes(1);
    } finally {
      unmount();
    }
    expect(FakeEventSource.instances[0]!.close).toHaveBeenCalled();
  });

  it("rajada de avisos vira uma releitura em voo e uma depois, não uma por aviso", async () => {
    const releases: Array<() => void> = [];
    const refresh = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          releases.push(resolve);
        }),
    );
    const { unmount } = await withMountedBrowser(() => useProductionLive(refresh, () => 30_000));
    try {
      const source = FakeEventSource.instances[0]!;
      source.open();
      for (let i = 0; i < 5; i++) source.emit("backstage-production-update");
      expect(refresh).toHaveBeenCalledTimes(1);
      releases.shift()?.();
      await vi.advanceTimersByTimeAsync(0);
      expect(refresh).toHaveBeenCalledTimes(2);
      releases.shift()?.();
      await vi.advanceTimersByTimeAsync(0);
      expect(refresh).toHaveBeenCalledTimes(2);
    } finally {
      unmount();
    }
  });

  it("volta a ouvir depois do 502 de deploy e cobre o que passou no meio", async () => {
    const refresh = vi.fn();
    const { value, unmount } = await withMountedBrowser(() => useProductionLive(refresh, () => 30_000));
    try {
      FakeEventSource.instances[0]!.open();
      FakeEventSource.instances[0]!.failForGood();
      await vi.advanceTimersByTimeAsync(2_000);
      expect(FakeEventSource.instances).toHaveLength(2);
      FakeEventSource.instances[1]!.open();
      await vi.advanceTimersByTimeAsync(0);
      expect(value.realtime.value).toBe("live");
      expect(refresh).toHaveBeenCalledTimes(1);
    } finally {
      unmount();
    }
  });
});

describe("as telas de lote ouvem o canal (WP-F15, P1-17)", () => {
  beforeEach(() => {
    env.reset();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.stubGlobal("onMounted", () => {});
    vi.stubGlobal("onBeforeUnmount", () => {});
  });

  const screens: Array<[string, () => { realtime: { value: string } }, number]> = [
    ["Finalização e Qualidade (useQcKiosk)", () => useQcKiosk(), 30_000],
    ["Cozinha (useProductionKds)", () => useProductionKds(), 30_000],
    ["Preparação (useMiseEnPlace)", () => useMiseEnPlace(ref("2026-11-26")), 60_000],
    ["Letreiro (useProductionForecast)", () => useProductionForecast(), 30_000],
  ];

  it.each(screens)("%s: o aviso refaz o fetch canônico e o selo sabe se é ao vivo", async (_name, build, cadence) => {
    const { value, unmount } = await withMountedBrowser(build);
    try {
      const source = FakeEventSource.instances[0]!;
      expect(source.url).toBe("/sse/production");
      expect(value.realtime.value).not.toBe("live");
      expect(pollInterval()()).toBe(cadence);
      source.open();
      expect(value.realtime.value).toBe("live");
      expect(pollInterval()()).toBe(Math.max(cadence, PRODUCTION_LIVE_RESERVE_POLL_MS));
      env.refresh.mockClear();
      source.emit("backstage-production-update");
      await vi.advanceTimersByTimeAsync(0);
      expect(env.refresh).toHaveBeenCalledTimes(1);
    } finally {
      unmount();
    }
  });

  it("Preparação: a lista e as marcas relêem pelo MESMO stream", async () => {
    const { unmount } = await withMountedBrowser(() => {
      const date = ref("2026-11-26");
      useMiseEnPlace(date);
      usePrepMarks(date);
    });
    try {
      expect(FakeEventSource.instances).toHaveLength(1);
      FakeEventSource.instances[0]!.open();
      env.refresh.mockClear();
      FakeEventSource.instances[0]!.emit("backstage-production-update");
      await vi.advanceTimersByTimeAsync(0);
      expect(env.refresh).toHaveBeenCalledTimes(2);
    } finally {
      unmount();
    }
  });
});
