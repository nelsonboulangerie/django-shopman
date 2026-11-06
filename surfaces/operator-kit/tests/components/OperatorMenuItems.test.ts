// "Sair deste dispositivo" no menu do operador (beta 05/11/2026, CEN-07): só
// havia Bloquear, e no celular de quem entrou com senha a trava deixava a lista
// de operadores à mostra para quem achasse o dispositivo.
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import OperatorMenuItems from "../../app/components/OperatorMenuItems.vue";

const { fetchMock, sessionData } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  sessionData: { value: null as unknown },
}));

mockNuxtImport("$fetch", () => fetchMock);
mockNuxtImport("useNuxtData", () => () => ({ data: sessionData }));

vi.mock("../../app/composables/useOperatorCapacity", () => ({
  useOperatorCapacity: () => ({ reading: ref(null), authorized: ref(false), stale: ref(false) }),
}));
vi.mock("../../app/composables/useSuiteChrome", () => ({
  useSharedCapacity: () => ({ value: null }),
}));

const reload = vi.fn();
let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

async function mount() {
  mounted = await mountSuspended(OperatorMenuItems, {
    props: { mode: "rail", operatorName: "Joyce" },
    global: { stubs: { Icon: true } },
  });
  return mounted;
}

beforeEach(() => {
  fetchMock.mockReset().mockResolvedValue({ ok: true });
  reload.mockReset();
  vi.stubGlobal("location", { ...window.location, reload });
});

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  vi.unstubAllGlobals();
});

describe("OperatorMenuItems — Sair deste dispositivo", () => {
  it("fora de um posto, oferece sair, e sair encerra a sessão no servidor", async () => {
    sessionData.value = { station: "", operator: { id: 7, username: "joyce", name: "Joyce" } };
    const wrapper = await mount();

    const sair = wrapper.find("[data-operator-menu-sign-out]");
    expect(sair.exists()).toBe(true);
    expect(sair.text()).toContain("Sair deste dispositivo");

    await sair.trigger("click");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/operator/logout/",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("num posto, não oferece: lá a saída é o Bloquear, e o vínculo é da loja", async () => {
    sessionData.value = { station: "caixa-1", operator: { id: 7, username: "joyce", name: "Joyce" } };
    const wrapper = await mount();

    expect(wrapper.find("[data-operator-menu-sign-out]").exists()).toBe(false);
  });

  it("sem ninguém identificado, não há de onde sair", async () => {
    sessionData.value = { station: "", operator: null };
    const wrapper = await mount();

    expect(wrapper.find("[data-operator-menu-sign-out]").exists()).toBe(false);
  });
});
