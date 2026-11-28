// WP-F10: a lista das encomendas do produto na data, pela régua das reservas.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import LotCommitmentsDialog from "../../app/components/LotCommitmentsDialog.vue";
import { rowPromisedOrders } from "../../app/presentation/production";
import type {
  ProductionMatrixRowProjection,
  ProductionPromisedProjection,
  PromisedOrderProjection,
} from "../../app/types/production";
import { nuxtUiStubs } from "../support/nuxtUiStubs";

const TODAY = "2026-11-26";

function order(over: Partial<PromisedOrderProjection> = {}): PromisedOrderProjection {
  return {
    ref: "NB-261126-B57",
    customer_first_name: "Clara",
    due_time: "09:00",
    fulfillment_type: "pickup",
    qty: "1",
    status: "confirmed",
    status_label: "Confirmado",
    ...over,
  };
}

function promised(over: Partial<ProductionPromisedProjection> = {}): ProductionPromisedProjection {
  return {
    date: "2026-11-27",
    planned_qty: "42",
    ordered_qty: "1",
    free_qty: "41",
    over_plan_qty: "0",
    orders: [order()],
    ...over,
  };
}

function row(over: Partial<ProductionMatrixRowProjection> = {}): ProductionMatrixRowProjection {
  return {
    output_sku: "CROISSANT",
    recipe_name: "Croissant Manteiga",
    output_unit: "un",
    planned_orders: [],
    started_orders: [],
    finished_orders: [],
    promised: null,
    ...over,
  } as unknown as ProductionMatrixRowProjection;
}

describe("LotCommitmentsDialog", () => {
  beforeEach(() => {
    vi.stubGlobal("computed", computed);
    vi.stubGlobal("ref", ref);
    vi.stubGlobal("watch", watch);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("título com a grandeza, o dia, e uma linha por encomenda", () => {
    const r = row({
      promised: promised({
        ordered_qty: "3",
        orders: [
          order(),
          order({ ref: "NB-2", customer_first_name: "Marina", due_time: "11:30", fulfillment_type: "delivery", qty: "2" }),
        ],
      }),
    });
    const wrapper = mount(LotCommitmentsDialog, {
      props: { row: r, today: TODAY },
      global: { stubs: nuxtUiStubs },
    });
    const text = wrapper.text().replace(/\s+/g, " ");
    expect(text).toContain("3 un. encomendadas · Croissant Manteiga");
    expect(text).toContain("Encomendas de amanhã, sex 27/11, pela hora.");
    expect(wrapper.findAll("[data-promised-order]").map((li) => li.text().trim())).toEqual([
      "Clara · retirada · 9h · 1 un.",
      "Marina · entrega · 11h30 · 2 un.",
    ]);
    expect(wrapper.find("[data-promised-gap]").exists()).toBe(false);
    expect(text).not.toMatch(/R\$/);
    expect(rowPromisedOrders(r)).toHaveLength(2);
  });

  it("o que o plano não cobre aparece embaixo da lista", () => {
    const r = row({ promised: promised({ planned_qty: "0", free_qty: "0", over_plan_qty: "1" }) });
    const wrapper = mount(LotCommitmentsDialog, {
      props: { row: r, today: TODAY },
      global: { stubs: nuxtUiStubs },
    });
    expect(wrapper.get("[data-promised-gap]").text()).toBe("Nenhum lote planejado para esta data.");
  });
});
