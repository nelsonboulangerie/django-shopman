import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import KdsExpeditionCard from "../../app/components/KdsExpeditionCard.vue";
import type { KDSExpeditionCardProjection } from "../../app/types/kds";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);

function card(over: Partial<KDSExpeditionCardProjection> = {}): KDSExpeditionCardProjection {
  return {
    pk: 9,
    order_ref: "WEB-20260921-0131",
    channel_icon: "language",
    customer_name: "Rafael",
    fulfillment_icon: "local_shipping",
    fulfillment_label: "Entrega",
    is_delivery: true,
    units_count: "4",
    line_count: 2,
    total_display: "R$ 38,40",
    items: [{ sku: "A", name: "Pão de queijo", qty: 3, notes: "", stock_warning: "" }],
    is_scheduled: false,
    is_expedition: true,
    advance_block_label: "",
    advance_block_reason: "",
    test_order_label: "",
    ...over,
  };
}

const mountCard = (props: Record<string, unknown>) =>
  mount(KdsExpeditionCard, { props, global: { stubs: { Icon: true } } });

describe("KdsExpeditionCard — a mesma moldura do preparo", () => {
  it("despacho: o botão diz o ato e emite dispatch", async () => {
    const w = mountCard({ card: card() });
    const button = w.get("button:not([aria-expanded])");
    expect(button.text()).toContain("Despachar pedido");
    await button.trigger("click");
    expect(w.emitted("action")).toEqual([["dispatch"]]);
  });

  it("balcão: Entregar pedido emite complete", async () => {
    const w = mountCard({ card: card({ is_delivery: false, fulfillment_label: "Retirada", fulfillment_icon: "storefront" }) });
    const button = w.get("button:not([aria-expanded])");
    expect(button.text()).toContain("Entregar pedido");
    await button.trigger("click");
    expect(w.emitted("action")).toEqual([["complete"]]);
  });

  it("bloqueio do servidor: rótulo + motivo, e nenhum botão de saída", () => {
    const w = mountCard({
      card: card({
        advance_block_label: "Aguardando entregador iFood…",
        advance_block_reason: "Aguardando o iFood confirmar a retirada pelo entregador.",
      }),
    });
    const blocked = w.get("[data-testid='expedition-blocked']");
    expect(blocked.text()).toContain("Aguardando entregador iFood…");
    expect(blocked.text()).toContain("confirmar a retirada");
    expect(blocked.find("button").exists()).toBe(false);
    expect(w.text()).not.toContain("Despachar pedido");
  });

  it("o botão de saída nunca desce do alvo de toque (h-11), nem no compact", () => {
    for (const [density, height] of [
      ["compact", "h-11"],
      ["cozy", "h-11"],
      ["roomy", "h-14"],
    ] as const) {
      const button = mountCard({ card: card(), density }).get("button:not([aria-expanded])");
      expect(button.classes()).toContain(height);
    }
  });

  it("pedido de teste: o aviso proíbe ENTREGAR, antes do código", () => {
    const w = mountCard({ card: card({ test_order_label: "Pedido de teste do iFood" }) });
    const banner = w.get("[data-kds-test-order]");
    expect(banner.text()).toContain("não entregar");
    expect(w.html().indexOf("data-kds-test-order")).toBeLessThan(w.html().indexOf("0131"));
  });
});
