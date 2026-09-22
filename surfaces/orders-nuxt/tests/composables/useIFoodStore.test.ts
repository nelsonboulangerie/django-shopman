import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useIFoodStore } from "../../app/composables/useIFoodStore";

const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: { value: { operator: { id: 1 } } } }));

describe("useIFoodStore", () => {
  beforeEach(() => env.reset());

  it("lê a projeção da loja no iFood; sem resposta, é null", () => {
    env.fetchData.value = { enabled: true, pause: null };
    expect(useIFoodStore().store.value).toMatchObject({ enabled: true });
    env.fetchData.value = null;
    expect(useIFoodStore().store.value).toBeNull();
    expect(String(env.useFetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/ifood/store/");
  });

  it("pausar posta duração e motivo e adota a projeção devolvida", async () => {
    env.fetchMock.mockResolvedValueOnce({ enabled: true, pause: { state: "pending_create" } });
    const s = useIFoodStore();

    const ok = await s.pause("1h", "Cozinha cheia");

    expect(ok).toBe(true);
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/ifood/store/pause/");
    expect(env.fetchMock.mock.calls[0]![1]).toMatchObject({ method: "POST", body: { duration: "1h", reason: "Cozinha cheia" } });
    expect(s.store.value?.pause?.state).toBe("pending_create");
  });

  it("recusa do servidor vira toast com a frase dele e reconsulta", async () => {
    env.fetchMock.mockRejectedValueOnce({ data: { detail: "O iFood já está pausado. Retome antes de pausar de novo." } });
    const s = useIFoodStore();

    const ok = await s.pause("1h", "x");

    expect(ok).toBe(false);
    expect(env.sonner.error).toHaveBeenCalledWith("O iFood já está pausado. Retome antes de pausar de novo.");
    expect(env.refresh).toHaveBeenCalled();
  });

  it("retomar posta em /resume/", async () => {
    const s = useIFoodStore();
    await s.resume();
    expect(String(env.fetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/ifood/store/resume/");
  });
});
