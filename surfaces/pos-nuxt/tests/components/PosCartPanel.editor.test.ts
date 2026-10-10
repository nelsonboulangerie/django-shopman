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
    expect(wrapper.find("[data-pos-keyboard-hint]").text()).toContain("Digite a quantidade");
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

  it("folha (tablet e celular): fechada é a barra da ação do momento; puxada, a gaveta com as linhas", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ sheet: true, tabTitle: "Mesa 6" }) });
    const bar = wrapper.find("[data-pos-sheet-bar]");
    expect(bar.attributes("data-pos-sheet")).toBe("closed");
    // A linha de contexto: comanda, itens e cozinha; o número é o total confirmado.
    expect(bar.find("[data-operator-action-bar-context]").text()).toContain("Mesa 6 · 3 itens");
    expect(bar.find("[data-operator-action-bar-context]").text()).toContain("3 ainda não foram à cozinha");
    expect(bar.find("[data-operator-action-bar-context]").text()).toContain(formatBRL(1100));
    // Nada da comanda na tela enquanto a gaveta está fechada (sem véu sobre a folha).
    expect(wrapper.find("[data-receipt-list]").exists()).toBe(false);
    expect(document.body.querySelector("[data-pos-line-editor]")).toBeNull();
    expect(wrapper.find("[data-pos-sheet-backdrop]").exists()).toBe(false);
    // Com itens a enviar, Enviar à cozinha é a ação do momento.
    const action = bar.find("[data-operator-action-bar-action]");
    expect(action.text()).toContain("Enviar à cozinha");
    await action.trigger("click");
    expect(wrapper.emitted("fire")).toHaveLength(1);
    // "Ver a comanda" puxa a gaveta: linhas e o Pagamento dentro dela.
    await bar.find("[data-operator-action-bar-secondary]").trigger("click");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(wrapper.find("[data-pos-sheet-bar]").attributes("data-pos-sheet")).toBe("open");
    const drawer = document.body.querySelector('[data-pos-ticket][data-pos-sheet="open"]');
    expect(drawer?.querySelector("[data-receipt-list]")).not.toBeNull();
    expect(drawer?.querySelector("[data-pos-sheet-title]")?.textContent).toContain("Mesa 6 · 3 itens");
    (drawer?.querySelector("[data-pos-primary]") as HTMLButtonElement).click();
    expect(wrapper.emitted("prepare")).toHaveLength(1);
    (drawer?.querySelector('[aria-label="Recolher a comanda"]') as HTMLButtonElement).click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(wrapper.find("[data-pos-sheet-bar]").attributes("data-pos-sheet")).toBe("closed");
  });

  it("folha sem nada a enviar: o Pagamento é a ação do momento", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ items: [item({ sku: "PAO", name: "Pão", fired: true })], sheet: true }),
    });
    const action = wrapper.find("[data-pos-sheet-bar] [data-operator-action-bar-action]");
    expect(action.text()).toContain("Pagamento");
    await action.trigger("click");
    expect(wrapper.emitted("prepare")).toHaveLength(1);
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

// A GRADE DE CONTROLES (dono, 10/10): o bloco da linha (quantidade | Remover;
// Desconto | Observação) só com a linha aberta; o bloco da comanda (Enviar à cozinha |
// Dividir) sempre, logo acima do Pagamento.
describe("PosCartPanel — a grade de controles da comanda", () => {
  it("linha aberta: quantidade | Remover, Desconto | Observação; e a comanda embaixo", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const line = wrapper.find("[data-pos-controls-block='line']");
    expect(line.findAll("[data-pos-control-cell]").map((c) => c.attributes("data-pos-control-cell"))).toEqual(["qty", "remove", "discount", "note"]);
    const tab = wrapper.find("[data-pos-ticket-foot] [data-pos-controls-block='tab']");
    expect(tab.findAll("[data-pos-control-cell]").map((c) => c.attributes("data-pos-control-cell"))).toEqual(["fire", "split"]);
    // A dica do teclado mora no cabeçalho do editor, não no pé.
    expect(wrapper.find("[data-pos-line-editor] [data-pos-keyboard-hint]").exists()).toBe(true);
  });

  it("sem linha aberta, só Enviar | Dividir, no mesmo lugar", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find("[data-pos-line-editor-close]").trigger("click");
    expect(wrapper.find("[data-pos-controls-block='line']").exists()).toBe(false);
    expect(wrapper.findAll("[data-pos-ticket-foot] [data-pos-control-cell]")).toHaveLength(2);
  });

  it("Dividir pede o modal de dividir a conta", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find("[data-pos-split]").trigger("click");
    expect(wrapper.emitted("split")).toHaveLength(1);
  });

  it("tudo enviado: o Enviar diz o estado em palavra, apagado, e Dividir segue ao lado", async () => {
    const fired = [item({ sku: "PAO", name: "Pão", fired: true, fired_qty: 1 })];
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: fired }) });
    const send = wrapper.find("[data-pos-fire]");
    expect(send.text()).toContain("Enviado");
    expect(send.attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-pos-split]").exists()).toBe(true);
  });

  it("editando um pedido (Salvar alterações) não oferece Dividir", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ primaryLabel: "Salvar alterações" }) });
    expect(wrapper.find("[data-pos-split]").exists()).toBe(false);
  });

  it("Pagamento numa linha: sem o rótulo 'total' empilhado; sem conexão diz 'total sem conexão'", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-primary-total]").text()).not.toMatch(/total/);
    const offline = await mountSuspended(PosCartPanel, { props: props({ total: { status: "offline", display: formatBRL(1100) } }) });
    expect(offline.find("[data-pos-primary-total]").text()).toContain("total sem conexão");
    expect(offline.find("[data-pos-primary-total-value]").text()).toContain(formatBRL(1100));
  });
});

// UM PADRÃO PARA EDITAR UMA LINHA (dono, 10/10): desconto e observação abrem no bloco
// do editor, no lugar da grade, e terminam em Cancelar ou Aplicar. Sem modal.
describe("PosCartPanel — a edição da linha é sempre no editor", () => {
  it("observação: escrita no editor, Aplicar grava, sem modal", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find("[data-pos-line-note]").trigger("click");
    expect(wrapper.find("[data-pos-controls-block='line']").exists()).toBe(false);
    const panel = wrapper.find("[data-pos-note-panel]");
    expect(panel.exists()).toBe(true);
    expect(document.body.querySelector("[data-pos-note-dialog]")).toBeNull();
    await panel.find("textarea").setValue("Sem cebola");
    await panel.find("[data-pos-edit-apply]").trigger("click");
    expect(wrapper.emitted("setNotes")?.[0]).toEqual(["L-CAFE", "Sem cebola"]);
    expect(wrapper.find("[data-pos-note-panel]").exists()).toBe(false);
  });

  it("observação: Cancelar devolve a grade sem gravar", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find("[data-pos-line-note]").trigger("click");
    await wrapper.find("[data-pos-note-panel] textarea").setValue("x");
    await wrapper.find("[data-pos-edit-cancel]").trigger("click");
    expect(wrapper.emitted("setNotes")).toBeUndefined();
    expect(wrapper.find("[data-pos-controls-block='line']").exists()).toBe(true);
  });

  it("desconto: formato em duas colunas, rascunho até Aplicar; Cancelar não grava", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find("[data-pos-line-discount]").trigger("click");
    const panel = wrapper.find("[data-pos-discount-panel]");
    expect(panel.exists()).toBe(true);
    expect(wrapper.find("[data-pos-controls-block='line']").exists()).toBe(false);
    await wrapper.find('[aria-label="Dígito 5"]').trigger("click");
    await wrapper.find("[data-pos-edit-cancel]").trigger("click");
    expect(wrapper.emitted("setDiscount")).toBeUndefined();
    await wrapper.find("[data-pos-line-discount]").trigger("click");
    await wrapper.find('[aria-label="Dígito 5"]').trigger("click");
    await wrapper.find("[data-pos-edit-apply]").trigger("click");
    expect(wrapper.emitted("setDiscount")?.[0]?.slice(0, 2)).toEqual(["L-CAFE", 5]);
  });

  it("a dica do teclado diz o que as teclas fazem agora", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-keyboard-hint]").text()).toContain("Digite a quantidade");
    await wrapper.find("[data-pos-line-discount]").trigger("click");
    expect(wrapper.find("[data-pos-keyboard-hint]").text()).toContain("Enter aplica");
  });

});
