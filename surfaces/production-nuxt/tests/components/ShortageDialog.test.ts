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
