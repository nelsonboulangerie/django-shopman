// Beta 05/11 (GES-01): o app.vue, a fila e o sinal da fila chamavam
// `useChannelAttention`, e cada chamada abria o próprio `/sse/catalog` e o próprio poll.
// A fila chegava a 51 leituras de `/channels/attention/` em 6,5 min e a mais de cinco
// conexões longas; em HTTP/1.1 o POST de travar a tela ficava na fila. Agora: uma
// leitura, um poll e um stream por app, e a página do catálogo assina o MESMO stream.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { FakeEventSource } from "../../../operator-kit/tests/support/fakeEventSource";
import { ssePath } from "../../../operator-kit/app/utils/ssePath";
import { useBackstageEvents } from "../../app/composables/useBackstageEvents";
import { useChannelAttention } from "../../app/composables/useChannelAttention";

const env = installNuxtGlobals();
let mounts: Array<() => void> = [];
let unmounts: Array<() => void> = [];

describe("useChannelAttention: uma por app", () => {
  beforeEach(() => {
    env.reset();
    mounts = [];
    unmounts = [];
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("ssePath", ssePath);
    vi.stubGlobal("useNuxtData", () => ({ data: ref({ operator: { id: 4 } }) }));
    vi.stubGlobal("onMounted", (fn: () => void) => mounts.push(fn));
    vi.stubGlobal("onBeforeUnmount", (fn: () => void) => unmounts.push(fn));
    const listeners = { addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.stubGlobal("document", { ...listeners, visibilityState: "visible" });
    vi.stubGlobal("window", listeners);
    vi.useFakeTimers();
  });
  afterEach(() => {
    for (const unmount of unmounts) unmount();
    vi.useRealTimers();
    vi.stubGlobal("onMounted", () => {});
    vi.stubGlobal("onBeforeUnmount", () => {});
  });

  it("três chamadas, uma leitura, um poll e um /sse/catalog, dividido com a página do catálogo", async () => {
    env.fetchMock.mockResolvedValue({ attention: { label: "1 desligado" } });
    const calls = [useChannelAttention(), useChannelAttention(), useChannelAttention()];
    useBackstageEvents("catalog", vi.fn());
    for (const mount of mounts) mount();
    await vi.advanceTimersByTimeAsync(0);

    expect(new Set(calls.map((call) => call.attention)).size).toBe(1);
    expect(calls[0]!.attention.value?.label).toBe("1 desligado");
    const attentionReads = () =>
      env.fetchMock.mock.calls.filter(([url]) => url === "/api/v1/backstage/channels/attention/").length;
    expect(attentionReads()).toBe(1);
    expect(FakeEventSource.instances.filter((s) => s.url === "/sse/catalog")).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(60_000);
    expect(attentionReads()).toBe(2);
  });
});
