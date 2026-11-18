// WP-E2: a linha da encomenda de outro dia mostra a fornada planejada da data.
import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";

enableAutoUnmount(afterEach);

const fire: ActionAffordance = {
  ref: "fire_tab", present: true, label: "Enviar à cozinha", priority: "primary", enabled: true, reason: "", href: "/x",
};

function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { line_id: `L-${overrides.sku}`, price_q: 1600, qty: 1, notes: "", ...overrides };
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    items: [item({ sku: "BF", name: "Baguette de Tradition", qty: 200 }), item({ sku: "CAFE", name: "Café" })],
    total: { status: "confirmed", display: "R$ 3.201,00" },
    requiresTab: false,
    hasOpenTab: true,
    loading: false,
    saving: false,
    fireAction: fire,
    unfireAction: { ...fire, ref: "unfire_tab", label: "Cancelar envio" },
    firing: false,
    planBySku: { BF: { planned_qty: 22, free_qty: 22 } },
    planDate: "2026-11-17",
    ...overrides,
  };
}

describe("PosCartPanel: o lastro da encomenda na linha", () => {
  it("acima do plano: a linha diz a fornada da data e que passa do plano", async () => {
    const w = await mountSuspended(PosCartPanel, { props: props() });
    const fact = w.find("[data-pos-line-plan]");
    expect(fact.attributes("data-pos-line-plan")).toBe("over");
    expect(fact.text()).toBe("Passa do plano: 22 planejadas para 17/11");
    // O café não tem lastro informado: a linha dele não carrega fato de plano.
    expect(w.findAll("[data-pos-line-plan]")).toHaveLength(1);
  });

  it("dentro do plano: só a fornada da data", async () => {
    const w = await mountSuspended(PosCartPanel, {
      props: props({ items: [item({ sku: "BF", name: "Baguette de Tradition", qty: 20 })] }),
    });
    const fact = w.find("[data-pos-line-plan]");
    expect(fact.attributes("data-pos-line-plan")).toBe("within");
    expect(fact.text()).toBe("22 planejadas para 17/11");
  });

  it("o mesmo SKU em duas linhas soma contra o livre", async () => {
    const w = await mountSuspended(PosCartPanel, {
      props: props({
        items: [
          item({ sku: "BF", name: "Baguette de Tradition", qty: 12, line_id: "L1" }),
          item({ sku: "BF", name: "Baguette de Tradition", qty: 12, line_id: "L2" }),
        ],
      }),
    });
    expect(w.findAll('[data-pos-line-plan="over"]')).toHaveLength(2);
  });

  it("venda de hoje: nenhum fato de plano", async () => {
    const w = await mountSuspended(PosCartPanel, { props: props({ planBySku: {}, planDate: "" }) });
    expect(w.find("[data-pos-line-plan]").exists()).toBe(false);
  });
});
