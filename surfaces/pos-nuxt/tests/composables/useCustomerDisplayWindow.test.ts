import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import { bindPwaUpdateRegistration } from "../../../operator-kit/app/composables/usePwaUpdate";
import { useCustomerDisplayWindow } from "~/composables/useCustomerDisplay";

async function mountWindow() {
  let state!: ReturnType<typeof useCustomerDisplayWindow>;
  const wrapper = await mountSuspended(defineComponent({
    setup() {
      state = useCustomerDisplayWindow();
      return () => h("span");
    },
  }));
  return { state, wrapper };
}

afterEach(() => {
  bindPwaUpdateRegistration(null);
  vi.restoreAllMocks();
});

describe("abrir a tela do cliente", () => {
  it("reaproveita a MESMA janela nomeada em vez de empilhar outra", async () => {
    const open = vi.fn().mockReturnValue({} as Window);
    vi.stubGlobal("open", open);
    const { state, wrapper } = await mountWindow();

    expect(state.open()).toBe(true);
    expect(state.open()).toBe(true);
    expect(open).toHaveBeenNthCalledWith(1, "/display", "pos-customer-display");
    expect(open).toHaveBeenNthCalledWith(2, "/display", "pos-customer-display");
    wrapper.unmount();
  });

  it("pop-up bloqueado devolve false — quem avisa é a tela", async () => {
    vi.stubGlobal("open", vi.fn().mockReturnValue(null));
    const { state, wrapper } = await mountWindow();
    expect(state.open()).toBe(false);
    wrapper.unmount();
  });

  it("o gesto SONDA a versão: é a janela do operador que está presa, não a que abre", async () => {
    // A janela nova já nasce na versão nova (navegação é NetworkOnly). O que o
    // clique compra é descobrir AGORA o worker em espera, para a janela do
    // operador — aberta há dias — ter o que aplicar quando o balcão esvaziar.
    const checkForUpdate = vi.fn().mockResolvedValue(true);
    const updateServiceWorker = vi.fn();
    bindPwaUpdateRegistration({ needRefresh: ref(false), updateServiceWorker, checkForUpdate });
    vi.stubGlobal("open", vi.fn().mockReturnValue({} as Window));
    const { state, wrapper } = await mountWindow();

    state.open();

    expect(checkForUpdate).toHaveBeenCalledOnce();
    // Sondar NUNCA aplica: quem troca de versão com o balcão cheio seria o PDV.
    expect(updateServiceWorker).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it("a sonda que falha não impede o operador de abrir a janela", async () => {
    bindPwaUpdateRegistration({
      needRefresh: ref(false),
      updateServiceWorker: vi.fn(),
      checkForUpdate: vi.fn().mockRejectedValue(new Error("offline")),
    });
    vi.stubGlobal("open", vi.fn().mockReturnValue({} as Window));
    const { state, wrapper } = await mountWindow();

    expect(state.open()).toBe(true);
    wrapper.unmount();
  });
});
