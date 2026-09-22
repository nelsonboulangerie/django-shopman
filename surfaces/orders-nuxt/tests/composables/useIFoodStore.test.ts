import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useIFoodStore } from "../../app/composables/useIFoodStore";

const env = installNuxtGlobals();
vi.stubGlobal("useNuxtData", () => ({ data: { value: { operator: { id: 1 } } } }));

describe("useIFoodStore", () => {
  beforeEach(() => env.reset());

  it("lê a projeção da loja no iFood; sem resposta, é null", () => {
    env.fetchData.value = { enabled: true, channel_off: false };
    expect(useIFoodStore().store.value).toMatchObject({ enabled: true });
    env.fetchData.value = null;
    expect(useIFoodStore().store.value).toBeNull();
    expect(String(env.useFetchMock.mock.calls[0]![0])).toBe("/api/v1/backstage/ifood/store/");
  });

  it("não tem mais pausar/retomar: ligar e desligar é o toggle do card", () => {
    const s = useIFoodStore() as Record<string, unknown>;
    expect(s.pause).toBeUndefined();
    expect(s.resume).toBeUndefined();
  });
});
