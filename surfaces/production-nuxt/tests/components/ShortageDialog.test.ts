import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import ShortageDialog from "../../app/components/ShortageDialog.vue";
import type { ProductionShortageError } from "../../app/types/production";
import { nuxtUiStubs } from "../support/nuxtUiStubs";

// Beta 05/11: "MASSA-CROISSANT precisa 336000.000 · tem 18720.000", "Esta
// operação não está autorizada a ignorar a falta." e, ao fechar, o modal
// piscava "O lote undefined tem encomendas…".

const materialShortage = {
  code: "material_shortage",
  work_order_ref: "WO-2026-00022",
  idempotency_key: "k",
  possibilities: [{ kind: "retry", label: "Tentar novamente", enabled: true, proof: "" }],
  missing: [
    {
      sku: "MASSA-CROISSANT",
      name: "Massa Croissant",
      unit: "g",
      needed: "336000.000",
      available: "18720.000",
      shortage: "317280.000",
    },
  ],
} as unknown as ProductionShortageError;

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
});
afterEach(() => vi.unstubAllGlobals());

function mountDialog(shortage: ProductionShortageError | null) {
  return mount(ShortageDialog, {
    props: { shortage },
    global: { stubs: nuxtUiStubs },
  });
}

describe("ShortageDialog — falta de insumo", () => {
  it("nomeia o insumo, escreve a unidade e diz quem resolve", () => {
    const wrapper = mountDialog(materialShortage);
    const item = wrapper.get("[data-shortage-item]").text().replace(/\s+/g, " ");

    expect(item).toContain("Massa Croissant");
    expect(item).not.toContain("MASSA-CROISSANT");
    expect(item).toContain("precisa 336 kg · tem 18,72 kg · faltam 317,28 kg");
    expect(wrapper.html()).toContain("Peça ao gerente");
    expect(wrapper.html()).not.toContain("não está autorizada");
  });

  it("ao fechar, título e frase continuam os do último envelope", async () => {
    const wrapper = mountDialog(materialShortage);
    const modal = wrapper.findComponent({ name: "NuxtModal" });
    expect(modal.props("title")).toBe("Insumos insuficientes");

    await wrapper.setProps({ shortage: null });
    await nextTick();

    expect(modal.props("title")).toBe("Insumos insuficientes");
    expect(modal.props("description")).not.toContain("undefined");
  });
});

// WP-F06 (decisão 1 do dono, 23/11/2026): rendeu menos que o encomendado, o lote
// fecha com a verdade. Antes a tela mandava "informar pelo menos 6.000 un." e o
// "Revisar quantidade" não fazia nada.
const shortLot = {
  code: "order_shortage",
  work_order_ref: "WO-2026-00034",
  idempotency_key: "k",
  possibilities: [
    { kind: "retry", label: "Revisar quantidade", enabled: true, proof: "" },
    { kind: "confirm", label: "Fechar com 4", enabled: true, proof: "assinada" },
  ],
  required: "6.000",
  requested: "4.000",
  order_refs: ["NB-261123-B57"],
  orders: [{ ref: "NB-261123-B57", qty: "6" }],
} as unknown as ProductionShortageError;

describe("ShortageDialog — o lote curto fecha com a verdade", () => {
  function mountShortLot(allowShortLot: boolean) {
    return mount(ShortageDialog, {
      props: { shortage: shortLot, allowShortLot },
      global: { stubs: nuxtUiStubs },
    });
  }

  it("diz quanto rendeu, quanto falta e quem fica descoberto", () => {
    const wrapper = mountShortLot(true);
    const modal = wrapper.findComponent({ name: "NuxtModal" });

    expect(modal.props("title")).toBe("Rendeu menos que o encomendado");
    expect(modal.props("description")).toBe("Rendeu 4. Faltam 2 para as encomendas.");
    const order = wrapper.get("[data-short-lot-order]");
    expect(order.findAll("span").map((span) => span.text())).toEqual(["NB-261123-B57", "6 un."]);
    // Só o que é sempre verdade: a lista e o aviso ao Gestor saem de réguas diferentes
    // até o WP-F08 (#3457), então a tela não promete o aviso.
    expect(wrapper.get("[data-short-lot-outcome]").text()).toBe("O lote fecha com 4 e o pão entra no estoque.");
    expect(wrapper.html()).not.toContain("Promessa em risco");
    expect(wrapper.html()).not.toContain("pelo menos");
  });

  it("fecha com a prova da recusa, e revisar devolve à contagem", async () => {
    const wrapper = mountShortLot(true);

    expect(wrapper.get("[data-short-lot-confirm]").text()).toBe("Fechar com 4");
    await wrapper.get("[data-short-lot-confirm]").trigger("click");
    await wrapper.get("[data-short-lot-review]").trigger("click");

    expect(wrapper.emitted("close-short-lot")).toEqual([["assinada"]]);
    expect(wrapper.emitted("review")).toHaveLength(1);
  });

  it("uma unidade e um pedido no singular", () => {
    const wrapper = mount(ShortageDialog, {
      props: { shortage: { ...shortLot, required: "2", requested: "1" } as ProductionShortageError, allowShortLot: true },
      global: { stubs: nuxtUiStubs },
    });

    expect(wrapper.findComponent({ name: "NuxtModal" }).props("description")).toBe("Rendeu 1. Falta 1 para as encomendas.");
    expect(wrapper.get("[data-short-lot-outcome]").text()).toBe("O lote fecha com 1 e o pão entra no estoque.");
  });

  it("rendeu zero: não diz que o pão entra no estoque", () => {
    const wrapper = mount(ShortageDialog, {
      props: { shortage: { ...shortLot, requested: "0" } as ProductionShortageError, allowShortLot: true },
      global: { stubs: nuxtUiStubs },
    });

    expect(wrapper.findComponent({ name: "NuxtModal" }).props("description")).toBe("Rendeu 0. Faltam 6 para as encomendas.");
    expect(wrapper.get("[data-short-lot-outcome]").text()).toBe("O lote fecha sem nada para o estoque.");
  });

  it("a tela que não sabe fechar o lote curto não oferece o botão", () => {
    const wrapper = mountShortLot(false);

    expect(wrapper.find("[data-short-lot-confirm]").exists()).toBe(false);
    expect(wrapper.findComponent({ name: "NuxtModal" }).props("title")).toBe("Quantidade não cobre pedidos");
  });
});
