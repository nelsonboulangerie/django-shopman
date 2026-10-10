// O cartão "Dinheiro da comanda" sempre pode sair (dono, 10/10/2026: "tem que
// ter um dismiss daquela porcaria de aviso"). Antes a saída só existia depois de
// uma falha, e o cartão ficava de pé no topo de toda venda seguinte.
import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosDrawerPulseCard from "~/components/PosDrawerPulseCard.vue";

const PENDING = { orderRef: "PDV-1012", tabDisplay: "6", changeQ: 4500 };

async function render(props: Record<string, unknown> = {}) {
  return mountSuspended(PosDrawerPulseCard, {
    props: { pending: PENDING, terminalLabel: "Balcão", state: "idle", message: "", compact: true, ...props },
  });
}

describe("PosDrawerPulseCard — a saída do cartão", () => {
  it("parado, o cartão sai com Visto", async () => {
    const wrapper = await render();
    const dismiss = wrapper.get("[data-drawer-dismiss]");

    expect(dismiss.text()).toBe("Visto");
    await dismiss.trigger("click");
    expect(wrapper.emitted("dismiss")).toHaveLength(1);
  });

  it("depois de uma falha, a saída diz o que aconteceu: abriu na chave", async () => {
    const wrapper = await render({ state: "uncertain", message: "Olhe a gaveta do Balcão antes de pedir de novo." });

    expect(wrapper.get("[data-drawer-dismiss]").text()).toBe("Abri com a chave");
  });

  it("enquanto o pedido está indo, a saída espera a resposta", async () => {
    const wrapper = await render({ state: "sending" });

    expect(wrapper.get("[data-drawer-dismiss]").attributes("disabled")).toBeDefined();
  });

  it("aberta, o cartão sai sozinho e não oferece saída", async () => {
    const wrapper = await render({ state: "sent", message: "Gaveta do Balcão aberta." });

    expect(wrapper.find("[data-drawer-dismiss]").exists()).toBe(false);
  });
});
