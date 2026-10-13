import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";
import { formatBRL } from "~/utils/posIntent";

enableAutoUnmount(afterEach);

// A CAIXA DE MARCAR DIZ O QUE ACONTECEU NO MESMO QUADRO DO TOQUE (dono, 13/10/2026).
// Defeito: marcar UMA linha não marcava nada. A regra antiga juntava a linha aberta como
// "primeira marcada" e transformava conjunto de um em "linha aberta": a caixa clicada
// ficava vazia (ou marcava duas, a aberta junto), e a caixa da própria linha aberta não
// fazia nada. O operador clicava de novo, ou em outra, sem saber se tinha aceitado.

function affordance(overrides: Partial<ActionAffordance> = {}): ActionAffordance {
  return { ref: "fire_tab", present: true, label: "Enviar à cozinha", priority: "primary", enabled: true, reason: "", href: "/x", ...overrides };
}
function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { line_id: `L-${overrides.sku}`, price_q: 500, qty: 1, notes: "", ...overrides };
}
function props() {
  return {
    items: [
      item({ sku: "PAO", name: "Pão" }),
      item({ sku: "QUICHE", name: "Quiche", price_q: 2490 }),
      item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 }),
    ],
    total: { status: "confirmed", display: formatBRL(3590) },
    requiresTab: false,
    hasOpenTab: true,
    loading: false,
    saving: false,
    fireAction: affordance(),
    unfireAction: affordance({ ref: "unfire_tab", label: "Cancelar envio" }),
    firing: false,
  };
}
type Wrapper = Awaited<ReturnType<typeof mountSuspended>>;
const marked = (wrapper: Wrapper) =>
  wrapper.findAll("[data-pos-line-marked]").map((li) => li.find("[data-item-select]").attributes("data-item-select"));
const ticked = (wrapper: Wrapper, lineId: string) =>
  wrapper.find(`[data-pos-line-mark="${lineId}"] [role="checkbox"]`).attributes("aria-checked");
const box = (wrapper: Wrapper, lineId: string) => wrapper.find(`[data-pos-line-mark="${lineId}"]`);

describe("PosCartPanel — a caixa de marcar responde no mesmo toque", () => {
  it("a caixa da linha aberta marca ela, e só ela", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // O editor nasce aberto na última lançada (Café).
    await box(wrapper, "L-CAFE").trigger("click");
    expect(marked(wrapper)).toEqual(["L-CAFE"]);
    expect(ticked(wrapper, "L-CAFE")).toBe("true");
  });

  it("a caixa de outra linha marca só a clicada (a aberta não entra junto)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await box(wrapper, "L-PAO").trigger("click");
    expect(marked(wrapper)).toEqual(["L-PAO"]);
    expect(ticked(wrapper, "L-PAO")).toBe("true");
    expect(ticked(wrapper, "L-CAFE")).toBe("false");
    // Uma marcada é o bloco dela, com a quantidade.
    expect(wrapper.find("[data-pos-line-editor-title]").text()).toContain("Pão");
  });

  it("com nada marcado, o primeiro clique já marca", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-line-editor]").exists()).toBe(false);
    await box(wrapper, "L-QUICHE").trigger("click");
    expect(marked(wrapper)).toEqual(["L-QUICHE"]);
  });

  it("clicar de novo desmarca", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await box(wrapper, "L-PAO").trigger("click");
    await box(wrapper, "L-PAO").trigger("click");
    expect(marked(wrapper)).toEqual([]);
    expect(ticked(wrapper, "L-PAO")).toBe("false");
  });

  it("Espaço na linha marca só ela", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[data-item-select="L-PAO"]').trigger("keydown", { key: " " });
    expect(marked(wrapper)).toEqual(["L-PAO"]);
  });

  it("Shift + clique marca o intervalo a partir da última marcada", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await box(wrapper, "L-PAO").trigger("click");
    await box(wrapper, "L-CAFE").trigger("click", { shiftKey: true });
    expect(marked(wrapper)).toEqual(["L-PAO", "L-QUICHE", "L-CAFE"]);
  });
});
