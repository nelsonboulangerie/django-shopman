import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, nextTick, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import LotCancelDialog from "../../app/components/LotCancelDialog.vue";
import LotVoidStakes from "../../app/components/LotVoidStakes.vue";
import { lotStakes } from "../../app/presentation/lotStakes";
import type {
  ProductionMatrixRowProjection,
  PromisedOrderProjection,
  WorkOrderCardProjection,
} from "../../app/types/production";
import { nuxtUiStubs } from "../support/nuxtUiStubs";

// WP-F07 (P0-1 a tela, P1-01): quem cancela ou tira um lote do plano lê, antes do
// botão, quantas unidades e quais pedidos dependem dele, e dá o motivo. Medido em
// 23/11: com 7 un. encomendadas o diálogo dizia só "o vínculo com pedidos é
// desfeito", e o motivo vazio virava "Cancelado pelo operador" no código.

function commitment(
  ref: string,
  qty: string,
  due = "",
  name = "",
  fulfillment = "",
): PromisedOrderProjection {
  return {
    ref,
    customer_first_name: name,
    due_time: due,
    fulfillment_type: fulfillment,
    qty,
    status: "confirmed",
    status_label: "Confirmado",
  };
}

const SEVEN_IN_FOUR = [
  commitment("NB-261123-A01", "2", "08:30", "Clara", "pickup"),
  commitment("NB-261123-A02", "2", "09:00", "Marina", "delivery"),
  commitment("NB-261123-A03", "2", "", "Ana"),
  commitment("NB-261123-A04", "1", "10:00"),
];

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
});
afterEach(() => vi.unstubAllGlobals());

describe("lotStakes: o que está encomendado, numa frase", () => {
  it("soma as unidades e conta os pedidos", () => {
    expect(lotStakes(SEVEN_IN_FOUR, "un")?.headline).toBe("7 un. encomendadas: 4 pedidos");
  });

  it("uma unidade, um pedido: singular", () => {
    expect(lotStakes([commitment("NB-1", "1")], "un")?.headline).toBe("1 un. encomendada: 1 pedido");
  });

  it("sem encomenda não há número: a tela diz que nada depende do lote", () => {
    expect(lotStakes([], "un")).toBeNull();
  });
});

function mountStakes(orders: PromisedOrderProjection[], reason = "") {
  const model = ref(reason);
  const wrapper = mount(LotVoidStakes, {
    props: {
      orders,
      unit: "un",
      consequence: "O lote volta atrás.",
      reason: model.value,
      "onUpdate:reason": (value: string) => {
        model.value = value;
        void wrapper.setProps({ reason: value });
      },
    },
    global: { stubs: nuxtUiStubs },
  });
  return { wrapper, model };
}

describe("LotVoidStakes: o aviso e o motivo", () => {
  it("com encomenda: número, pedidos e hora antes de qualquer botão", () => {
    const { wrapper } = mountStakes(SEVEN_IN_FOUR);
    const alert = wrapper.get("[data-lot-stakes-orders]").text().replace(/\s+/g, " ");

    expect(alert).toContain("7 un. encomendadas: 4 pedidos");
    const lines = wrapper
      .findAll("[data-lot-stakes-orders] li")
      .map((li) => li.text().replace(/\s+/g, " ").trim());
    // Primeiro nome, modo e hora (WP-F10); sem nome, o código do pedido.
    expect(lines).toEqual([
      "Clara · retirada · 8h30 · 2 un.",
      "Marina · entrega · 9h · 2 un.",
      "Ana · 2 un.",
      "NB-261123-A04 · 10h · 1 un.",
    ]);
    expect(alert).toContain("Promessa em risco");
    expect(wrapper.find("[data-lot-stakes-free]").exists()).toBe(false);
  });

  it("sem encomenda: diz que nada depende do lote", () => {
    const { wrapper } = mountStakes([]);
    expect(wrapper.get("[data-lot-stakes-free]").text()).toContain(
      "O lote volta atrás. Nenhuma encomenda depende dele.",
    );
  });

  it("um toque preenche o motivo; Outro limpa para escrever", async () => {
    const { wrapper, model } = mountStakes([]);
    const presets = wrapper.findAll("[data-lot-void-preset]");
    expect(presets.map((preset) => preset.text())).toEqual([
      "Planejado a mais",
      "Falta insumo",
      "Massa perdida",
    ]);

    await presets[1]!.trigger("click");
    expect(model.value).toBe("Falta insumo");

    await wrapper.get("[data-lot-void-other]").trigger("click");
    await nextTick();
    expect(model.value).toBe("");
    expect(wrapper.get("[data-lot-void-other]").attributes("aria-pressed")).toBe("true");
  });
});

function card(over: Partial<WorkOrderCardProjection> = {}): WorkOrderCardProjection {
  return {
    pk: 34,
    ref: "WO-034",
    rev: 5,
    status: "planned",
    planned_qty: "40",
    started_qty: "",
    promised: {
      date: "2026-11-24",
      planned_qty: "40",
      ordered_qty: "7",
      free_qty: "33",
      over_plan_qty: "0",
      orders: SEVEN_IN_FOUR,
    },
    can_void: true,
    ...over,
  } as WorkOrderCardProjection;
}

function mountCancel(over: Record<string, unknown> = {}) {
  const order = (over.selectedOrder as WorkOrderCardProjection | undefined) ?? card();
  return mount(LotCancelDialog, {
    props: {
      row: { output_sku: "CROISSANT", output_unit: "un", started_orders: [], planned_orders: [order] } as unknown as ProductionMatrixRowProjection,
      title: "Croissant",
      description: "",
      orders: [order],
      selectedOrder: order,
      voidConfirming: true,
      voidSubmitting: false,
      oldDoughAction: undefined,
      deviationAction: undefined,
      kdsCard: undefined,
      voidReason: "",
      ...over,
    },
    global: { stubs: nuxtUiStubs },
  });
}

describe("LotCancelDialog: cancelar diz o que está em jogo", () => {
  it("o aviso das encomendas vem antes do botão, e o botão espera o motivo", () => {
    const wrapper = mountCancel();
    const html = wrapper.html();

    expect(wrapper.text()).toContain("7 un. encomendadas: 4 pedidos");
    expect(html.indexOf("data-lot-stakes-orders")).toBeLessThan(html.indexOf("data-confirm-void"));
    expect(wrapper.get("[data-confirm-void]").attributes("disabled")).toBeDefined();
  });

  it("com motivo, confirma", async () => {
    const wrapper = mountCancel({ voidReason: "Massa perdida" });
    const confirm = wrapper.get("[data-confirm-void]");
    expect(confirm.attributes("disabled")).toBeUndefined();
    await confirm.trigger("click");
    expect(wrapper.emitted("confirm-void")).toHaveLength(1);
  });

  it("enquanto cancela, o botão fica ocupado e diz o que está fazendo (#3393)", () => {
    const wrapper = mountCancel({ voidReason: "Massa perdida", voidSubmitting: true });
    const confirm = wrapper.get("[data-confirm-void]");
    expect(confirm.attributes("disabled")).toBeDefined();
    expect(confirm.attributes("aria-busy")).toBe("true");
    expect(confirm.text()).toBe("Cancelando…");
  });

  it("sem permissão de cancelar não há botão: a tela diz quem cancela", () => {
    const order = card({ can_void: false });
    const wrapper = mountCancel({ selectedOrder: order, orders: [order], voidConfirming: false });
    expect(wrapper.find("[data-confirm-void]").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Cancelar lote…");
    expect(wrapper.get("[data-void-hint]").text()).toBe("Cancelar lote é com o gerente.");
  });
});
