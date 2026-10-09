// V4-PDV (`pos-sale4.html`): a comanda é lista + total + Pagamento; o editor da linha
// aparece sob demanda, colado no pé da lista, e o teclado físico edita a linha ativa.
import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";
import { formatBRL } from "~/utils/posIntent";

enableAutoUnmount(afterEach);

const fire: ActionAffordance = {
  ref: "fire_tab",
  present: true,
  label: "Enviar à cozinha",
  priority: "primary",
  enabled: true,
  reason: "",
  href: "/x",
};

function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { line_id: `L-${overrides.sku}`, price_q: 500, qty: 1, notes: "", ...overrides };
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    items: [item({ sku: "PAO", name: "Pão" }), item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 })],
    // O total é o da revisão do servidor (`saleTotalView`); aqui, já confirmado.
    total: { status: "confirmed", display: formatBRL(1100) },
    requiresTab: false,
    hasOpenTab: true,
    loading: false,
    saving: false,
    fireAction: fire,
    unfireAction: { ...fire, ref: "unfire_tab", label: "Cancelar envio" },
    firing: false,
    ...overrides,
  };
}

function press(key: string) {
  document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
}

describe("PosCartPanel — editor da linha sob demanda (v4)", () => {
  it("abre para a última lançada, diz o que edita, e Fechar devolve a lista inteira", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const editor = () => wrapper.find("[data-pos-line-editor]");
    expect(editor().exists()).toBe(true);
    expect(editor().text()).toContain("Editando");
    expect(editor().text()).toContain("Café");
    expect(editor().text()).toContain(`${formatBRL(300)} cada`);
    await wrapper.find("[data-pos-line-editor-close]").trigger("click");
    expect(editor().exists()).toBe(false);
    // Tocar uma linha reabre o editor DELA.
    await wrapper.find('[aria-label="Editar Pão"]').trigger("click");
    expect(editor().text()).toContain("Pão");
  });

  it("Esc fecha o editor; o próximo dígito do teclado físico o traz de volta e edita a linha", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    press("Escape");
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-pos-line-editor]").exists()).toBe(false);
    press("3");
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-pos-line-editor]").exists()).toBe(true);
    expect(wrapper.emitted("setQty")?.[0]).toEqual(["L-CAFE", 3]);
  });

  it("Del pede a remoção da linha ativa, sempre com confirmação", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props(), attachTo: document.body });
    press("Delete");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.trim() === "Remover item");
    expect(confirm).toBeTruthy();
  });

  it("↑↓ trocam a linha do editor quando o foco não está num campo", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    press("ArrowUp");
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-pos-line-editor]").text()).toContain("Pão");
  });

  it("no balcão (sem toque) o numérico da tela só aparece no desconto", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-line-numpad]").exists()).toBe(false);
    expect(wrapper.find("[data-pos-keyboard-hint]").text()).toContain("Digite para mudar a quantidade");
    await wrapper.find("[data-pos-line-discount]").trigger("click");
    expect(wrapper.find("[data-pos-line-numpad]").exists()).toBe(true);
    expect(wrapper.find("[data-pos-discount-panel]").exists()).toBe(true);
  });

  it("o cabeçalho conta itens e linhas, e Enviar à cozinha mora nele com a contagem", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("h3").text()).toBe("3 itens");
    expect(wrapper.text()).toContain("em 2 linhas");
    const send = wrapper.find("[data-pos-fire]");
    expect(send.text()).toContain("Enviar à cozinha");
    expect(send.text()).toContain("3");
    await send.trigger("click");
    expect(wrapper.emitted("fire")).toHaveLength(1);
  });

  it("folha (tablet e celular): fechada mostra o resumo e o Pagamento; puxada mostra as linhas", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ sheet: true }) });
    expect(wrapper.find("[data-pos-ticket]").attributes("data-pos-sheet")).toBe("closed");
    expect(wrapper.find("[data-pos-sheet-summary]").text()).toContain("3 itens");
    expect(wrapper.find("[data-pos-sheet-summary]").text()).toContain(formatBRL(1100));
    expect(wrapper.find("[data-pos-line-editor]").exists()).toBe(false);
    expect(wrapper.find("[data-receipt-list]").attributes("style") ?? "").toContain("display: none");
    await wrapper.find("[data-pos-sheet-primary]").trigger("click");
    expect(wrapper.emitted("prepare")).toHaveLength(1);
    await wrapper.find("[data-pos-sheet-summary]").trigger("click");
    expect(wrapper.find("[data-pos-ticket]").attributes("data-pos-sheet")).toBe("open");
    expect(wrapper.find("[data-receipt-list]").attributes("style") ?? "").not.toContain("display: none");
    expect(wrapper.find("[data-pos-primary]").exists()).toBe(true);
    await wrapper.find('[aria-label="Recolher a comanda"]').trigger("click");
    expect(wrapper.find("[data-pos-ticket]").attributes("data-pos-sheet")).toBe("closed");
  });

  it("Pagamento é uma faixa só, com o total dentro", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const primary = wrapper.find("[data-pos-primary]");
    expect(primary.text()).toContain("Pagamento");
    expect(primary.text()).toContain(formatBRL(1100));
    await primary.trigger("click");
    expect(wrapper.emitted("prepare")).toHaveLength(1);
  });
});
