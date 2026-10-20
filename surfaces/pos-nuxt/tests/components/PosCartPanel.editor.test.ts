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

type Wrapper = Awaited<ReturnType<typeof mountSuspended>>;
/** Tocar a linha marca só ela e abre o bloco dela (dono, 13/10/2026). */
async function open(wrapper: Wrapper, name = "Café") {
  await wrapper.find(`[aria-label="Editar ${name}"]`).trigger("click");
}

function press(key: string) {
  document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
}

describe("PosCartPanel — editor da linha sob demanda (v4)", () => {
  it("nada marcado ao abrir; tocar a linha marca só ela e abre o bloco dela; o ✕ desmarca", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const editor = () => wrapper.find("[data-pos-line-editor]");
    expect(editor().exists()).toBe(false);
    await open(wrapper);
    expect(editor().exists()).toBe(true);
    expect(wrapper.find('[data-pos-line-mark="L-CAFE"] [role="checkbox"]').attributes("aria-checked")).toBe("true");
    expect(editor().text()).toContain("Café");
    expect(editor().text()).toContain(`${formatBRL(300)} cada`);
    await wrapper.find("[data-pos-line-editor-close]").trigger("click");
    expect(editor().exists()).toBe(false);
    // Tocar outra linha abre o bloco DELA (marca só ela).
    await open(wrapper, "Pão");
    expect(editor().text()).toContain("Pão");
    expect(wrapper.findAll("[data-pos-line-marked]")).toHaveLength(1);
  });

  it("Esc desmarca; sem nada marcado, o dígito do teclado físico vai à última lançada SEM marcá-la", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await open(wrapper, "Pão");
    press("Escape");
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-pos-line-editor]").exists()).toBe(false);
    press("3");
    await wrapper.vm.$nextTick();
    // O F9 de quem lança e digita continua mandando a comanda inteira.
    expect(wrapper.find("[data-pos-line-editor]").exists()).toBe(false);
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
    await open(wrapper);
    press("ArrowUp");
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-pos-line-editor]").text()).toContain("Pão");
  });

  it("no balcão (sem toque) o numérico da tela só aparece no desconto", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await open(wrapper);
    expect(wrapper.find("[data-pos-line-numpad]").exists()).toBe(false);
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

// A GRADE DE CONTROLES (dono, 10/10; um lugar só, 13/10): com algo marcado, o bloco tem
// tudo o que age nos marcados (quantidade | Remover; Desconto | Observação; Enviar |
// Transferir); sem nada marcado, o pé tem Enviar | Transferir da comanda inteira.
describe("PosCartPanel — a grade de controles da comanda", () => {
  it("linha marcada: quantidade | Remover, Desconto | Observação, Enviar | Transferir, tudo no bloco", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await open(wrapper);
    const line = wrapper.find("[data-pos-controls-block='line']");
    expect(line.findAll("[data-pos-control-cell]").map((c) => c.attributes("data-pos-control-cell"))).toEqual(["qty", "remove", "discount", "note"]);
    const tab = wrapper.find("[data-pos-line-editor] [data-pos-controls-block='tab']");
    expect(tab.findAll("[data-pos-control-cell]").map((c) => c.attributes("data-pos-control-cell"))).toEqual(["fire", "transfer"]);
    expect(wrapper.find("[data-pos-ticket-foot] [data-pos-controls-block='tab']").exists()).toBe(false);
    expect(wrapper.find("[data-pos-fire]").text()).toContain("Enviar marcados");
    // Sem dica de teclado escrita: as teclas moram nos botões.
    expect(wrapper.find("[data-pos-keyboard-hint]").exists()).toBe(false);
  });

  it("sem nada marcado, o pé diz o que vale para a comanda: Enviar à cozinha | Transferir itens", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-controls-block='line']").exists()).toBe(false);
    expect(wrapper.findAll("[data-pos-ticket-foot] [data-pos-control-cell]")).toHaveLength(2);
    expect(wrapper.find("[data-pos-tab-transfer]").text()).toContain("Transferir itens");
    expect(wrapper.find("[data-pos-foot-hint]").text()).toBe("Toque num item: quantidade, desconto, observação.");
  });

  it("Transferir no pé abre o mesmo diálogo do F10 (sem marcas, a escolha é lá); Dividir conta não existe na venda", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    expect(wrapper.find("[data-pos-split]").exists()).toBe(false);
    expect(wrapper.find("[data-pos-ticket-foot]").text()).not.toContain("Dividir");
    await wrapper.find("[data-pos-tab-transfer]").trigger("click");
    expect(wrapper.emitted("move")).toEqual([[undefined]]);
  });

  it("tudo enviado: o Enviar diz o estado em palavra, apagado, e Transferir segue ao lado", async () => {
    const fired = [item({ sku: "PAO", name: "Pão", fired: true, fired_qty: 1 })];
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: fired }) });
    const send = wrapper.find("[data-pos-fire]");
    expect(send.text()).toContain("Enviado");
    expect(send.attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-pos-tab-transfer]").exists()).toBe(true);
  });

  it("editando um pedido (Salvar alterações) não oferece Transferir", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ primaryLabel: "Salvar alterações" }) });
    expect(wrapper.find("[data-pos-tab-transfer]").exists()).toBe(false);
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
    await open(wrapper);
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
    await open(wrapper);
    await wrapper.find("[data-pos-line-note]").trigger("click");
    await wrapper.find("[data-pos-note-panel] textarea").setValue("x");
    await wrapper.find("[data-pos-edit-cancel]").trigger("click");
    expect(wrapper.emitted("setNotes")).toBeUndefined();
    expect(wrapper.find("[data-pos-controls-block='line']").exists()).toBe(true);
  });

  it("desconto: formato em duas colunas, rascunho até Aplicar; Cancelar não grava", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await open(wrapper);
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

  it("desconto em R$ com mais de uma unidade diz por unidade e na linha, no editor e no selo", async () => {
    // A prévia é a REVISÃO do servidor com o desconto digitado: o painel pede
    // (`previewDiscount`), diz "Calculando…" no mesmo lugar e repete a resposta.
    const cafe = item({ sku: "CAFE", name: "Café", price_q: 300, qty: 3, list_price_q: 300 });
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [item({ sku: "PAO", name: "Pão" }), cafe] }) });
    await open(wrapper);
    await wrapper.find("[data-pos-line-discount]").trigger("click");
    const reais = wrapper.findAll("[data-pos-discount-panel] button").find((b) => b.text() === "Em R$");
    await reais!.trigger("click");
    await wrapper.find('[aria-label="Dígito 1"]').trigger("click");
    expect(wrapper.emitted("previewDiscount")?.at(-1)).toEqual(["L-CAFE", "fixed", 1]);
    const reach = () => wrapper.find("[data-pos-discount-reach]");
    expect(reach().text()).toBe("Calculando…");
    expect(reach().attributes("aria-busy")).toBe("true");
    await wrapper.setProps({
      discountPreview: {
        lineId: "L-CAFE", kind: "fixed", value: 1, status: "ready",
        price: { list_price_q: 300, charged_price_q: 200, pricing_discount: null, manual_discount_discarded: false },
      },
    });
    expect(reach().text()).toBe(`${formatBRL(100)} por unidade · ${formatBRL(300)} na linha`);
    // Em %: o valor na linha também.
    const pct = wrapper.findAll("[data-pos-discount-panel] button").find((b) => b.text() === "Em %");
    await pct!.trigger("click");
    await wrapper.find('[aria-label="Dígito 1"]').trigger("click");
    await wrapper.find('[aria-label="Dígito 0"]').trigger("click");
    expect(wrapper.emitted("previewDiscount")?.at(-1)).toEqual(["L-CAFE", "percent", 10]);
    await wrapper.setProps({
      discountPreview: {
        lineId: "L-CAFE", kind: "percent", value: 10, status: "ready",
        price: { list_price_q: 300, charged_price_q: 270, pricing_discount: null, manual_discount_discarded: false },
      },
    });
    expect(reach().text()).toBe(`10% · ${formatBRL(90)} na linha`);

    const discounted = await mountSuspended(PosCartPanel, {
      props: props({
        items: [{ ...cafe, charged_price_q: 200, discount: { type: "fixed", value: 1, reason: "cortesia" } }],
      }),
    });
    const fact = discounted.find("[data-line-discount-fact]").text();
    expect(fact).toBe(`−${formatBRL(100)} por unidade · −${formatBRL(300)} na linha`);
  });

  it("o desconto que o motor descartaria se diz no editor, antes do Aplicar", async () => {
    const tab = item({
      sku: "TAB", name: "Tabatière", price_q: 600, qty: 2, list_price_q: 600, charged_price_q: 510,
      pricing_discount: { type: "promotion", label: "Semana do Pão", amount_q: 90, percent: 15 },
    });
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [tab] }) });
    await open(wrapper, "Tabatière");
    await wrapper.find("[data-pos-line-discount]").trigger("click");
    await wrapper.find('[aria-label="Dígito 1"]').trigger("click");
    await wrapper.find('[aria-label="Dígito 0"]').trigger("click");
    await wrapper.setProps({
      discountPreview: {
        lineId: "L-TAB", kind: "percent", value: 10, status: "ready",
        price: {
          list_price_q: 600, charged_price_q: 510, manual_discount_discarded: true,
          pricing_discount: { type: "promotion", label: "Semana do Pão", amount_q: 90, percent: 15 },
        },
      },
    });
    expect(wrapper.find("[data-pos-discount-reach]").text()).toBe('Não vale: "Semana do Pão" é maior');
  });

  it("linha com o preço a caminho: o total dela diz calculando, na largura do número", async () => {
    const cafe = item({
      sku: "CAFE", name: "Café", price_q: 300, qty: 3, list_price_q: 300, charged_price_q: 300,
      discount: { type: "fixed", value: 1, reason: "cortesia" }, price_pending: true,
    });
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [cafe] }) });
    const pending = wrapper.find("[data-pos-line-total-pending]");
    expect(pending.exists()).toBe(true);
    expect(pending.text()).toBe("Calculando");
    // O número de antes fica invisível, segurando a largura: nada pula.
    expect(pending.element.parentElement?.querySelector(".invisible")?.textContent).toBe(formatBRL(900));
  });

  it("as teclas moram nos botões, não numa frase: Remover diz Del, Enviar F9, Transferir F10", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await open(wrapper);
    expect(wrapper.find("[data-pos-keyboard-hint]").exists()).toBe(false);
    expect(wrapper.find("[data-pos-line-remove]").attributes("aria-keyshortcuts")).toBe("Delete");
    expect(wrapper.find("[data-pos-fire]").attributes("aria-keyshortcuts")).toBe("F9");
    expect(wrapper.find("[data-pos-tab-transfer]").attributes("aria-keyshortcuts")).toBe("F10");
  });

});
