// Uma coisa viva por app (beta 05/11, GES-01, PDV2-02, BI-21): o sino montado em quatro
// lugares abria quatro SSE e quatro polls. `useSharedLive` liga uma vez, no primeiro
// que monta, e desliga uma vez, quando o último desmonta.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import { useSharedLive } from "../app/composables/useSharedLive";
import { useNotifications } from "../app/composables/useNotifications";
import { installNuxtGlobals } from "./support/composableEnv";

const env = installNuxtGlobals();
let mounts: Array<() => void> = [];
let unmounts: Array<() => void> = [];

beforeEach(() => {
  env.reset();
  mounts = [];
  unmounts = [];
  vi.stubGlobal("onMounted", (fn: () => void) => mounts.push(fn));
  vi.stubGlobal("onBeforeUnmount", (fn: () => void) => unmounts.push(fn));
});
afterEach(() => {
  vi.stubGlobal("onMounted", () => {});
  vi.stubGlobal("onBeforeUnmount", () => {});
});

describe("useSharedLive", () => {
  it("roda o setup uma vez e liga o vivo só no primeiro que monta", () => {
    const setup = vi.fn(() => ({ count: ref(0) }));
    const stop = vi.fn();
    const live = vi.fn(() => stop);
    const a = useSharedLive("probe", setup, live);
    const b = useSharedLive("probe", setup, live);
    const c = useSharedLive("probe", setup, live);
    expect(a).toBe(b);
    expect(b).toBe(c);
    expect(setup).toHaveBeenCalledTimes(1);
    for (const mount of mounts) mount();
    expect(live).toHaveBeenCalledTimes(1);
    unmounts[0]!();
    unmounts[1]!();
    expect(stop).not.toHaveBeenCalled();
    unmounts[2]!();
    expect(stop).toHaveBeenCalledTimes(1);
    // Navegou e voltou: liga de novo, uma vez.
    mounts[0]!();
    expect(live).toHaveBeenCalledTimes(2);
  });

  it("cada app tem o seu: nada vaza entre requisições do servidor", () => {
    const setup = vi.fn(() => ({}));
    const first = useSharedLive("probe", setup, () => () => {});
    env.nuxtApp = {};
    const second = useSharedLive("probe", setup, () => () => {});
    expect(first).not.toBe(second);
    expect(setup).toHaveBeenCalledTimes(2);
  });
});

describe("useNotifications: uma caixa por app", () => {
  let session = ref<any>({ operator: { id: 1 } });
  beforeEach(() => {
    session = ref<any>({ operator: { id: 1 } });
    vi.stubGlobal("useNuxtData", () => ({ data: session }));
  });

  it("quatro sinos, um push e um poll", async () => {
    const starts = vi.fn(() => () => {});
    vi.stubGlobal("useUserNotifications", () => ({ realtime: ref("polling"), start: starts }));
    vi.useFakeTimers();
    try {
      const inboxes = [useNotifications(), useNotifications(), useNotifications(), useNotifications()];
      expect(new Set(inboxes.map(inbox => inbox.items)).size).toBe(1);
      for (const mount of mounts) mount();
      expect(starts).toHaveBeenCalledTimes(1);
      // A primeira leitura sai uma vez, não uma por sino.
      expect(env.fetchMock).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(0);
      env.fetchMock.mockClear();
      await vi.advanceTimersByTimeAsync(60_000);
      expect(env.fetchMock).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("marcar todas como lidas manda só as não lidas que estão na tela", async () => {
    vi.stubGlobal("useUserNotifications", () => ({ realtime: ref("polling"), start: () => () => {} }));
    const inbox = useNotifications();
    env.fetchMock.mockResolvedValueOnce({
      notifications: [
        { pk: 1, is_read: false },
        { pk: 2, is_read: true },
        { pk: 3, is_read: false },
      ],
      unread_count: 2,
    });
    await inbox.refresh();
    env.fetchMock.mockClear();
    env.fetchMock.mockResolvedValueOnce({ ok: true });
    env.fetchMock.mockResolvedValueOnce({ notifications: [], unread_count: 0 });
    await inbox.markAllRead();
    expect(env.fetchMock.mock.calls[0]).toEqual([
      "/api/v1/backstage/notifications/v2/seen/",
      { method: "POST", body: { notification_ids: [1, 3] } },
    ]);
  });

  it("'Não fui eu' pergunta antes: sem confirmação devolve o que vai acontecer", async () => {
    vi.stubGlobal("useUserNotifications", () => ({ realtime: ref("polling"), start: () => () => {} }));
    const inbox = useNotifications();
    env.fetchMock.mockRejectedValueOnce({
      statusCode: 409,
      data: { needs_confirmation: true, detail: "Isto encerra as sessões abertas da sua conta." },
    });
    const answer = await inbox.notMe(7, false);
    expect(answer).toEqual({ needsConfirmation: "Isto encerra as sessões abertas da sua conta." });
    expect(env.fetchMock).toHaveBeenCalledWith("/api/v1/backstage/notifications/7/action/", {
      method: "POST",
      body: { action: "not_me" },
    });
    env.fetchMock.mockResolvedValueOnce({ ok: true });
    env.fetchMock.mockResolvedValueOnce({ notifications: [], unread_count: 0 });
    expect(await inbox.notMe(7, true)).toBe("done");
    expect(env.fetchMock).toHaveBeenCalledWith("/api/v1/backstage/notifications/7/action/", {
      method: "POST",
      body: { action: "not_me", confirm: true },
    });
  });
});
