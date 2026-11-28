import { mountSuspended } from "@nuxt/test-utils/runtime";
import { DOMWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { VueWrapper } from "vue";

import OperatorReasonDialog from "../../app/components/OperatorReasonDialog.vue";

// O diálogo de motivo do kit, testado com o Modal, Alert, Select, Textarea e
// Button canônicos do Nuxt UI (o conteúdo é teleportado para document.body).

const mounted: VueWrapper[] = [];
async function mount(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(OperatorReasonDialog, {
    props: {
      open: true,
      title: "Cancelar a encomenda de Ana?",
      description: "O que já foi pago volta no mesmo meio.",
      confirmLabel: "Cancelar encomenda",
      ...props,
    },
    attachTo: document.body,
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

const dom = (selector: string) => new DOMWrapper(document.querySelector(selector) as Element);

describe("OperatorReasonDialog", () => {
  it("diz a consequência e confirma pelo rótulo de quem chama", async () => {
    const w = await mount();
    expect(document.body.textContent).toContain("O que já foi pago volta no mesmo meio.");
    const confirm = dom("[data-reason-confirm]");
    expect(confirm.text()).toBe("Cancelar encomenda");
    expect(confirm.attributes("disabled")).toBeUndefined();
    await dom("[data-reason-input]").setValue("  Cliente desistiu  ");
    await confirm.trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ reason: "Cliente desistiu", key: "" }]]);
  });

  it("motivo exigido: confirmar em branco não sai", async () => {
    await mount({ required: true });
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await dom("[data-reason-input]").setValue("Fora de área");
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeUndefined();
  });

  // Beta 05/11 (GES-14): o Cancelar apagado não dizia o que faltava.
  it("botão apagado diz o que falta, ao lado dele, e some quando há motivo", async () => {
    await mount({
      keyedReasons: [{ key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou." }],
    });
    expect(dom("[data-reason-missing]").text()).toBe("Escolha um motivo para confirmar.");
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    document.querySelector<HTMLElement>('[data-reason-keyed] [role="radio"][aria-label="Acabou um item"]')!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.querySelector("[data-reason-missing]")).toBeNull();
  });

  it("motivo da lista: escolher é obrigatório, mostra o que o cliente lê e o texto é interno", async () => {
    const keyedReasons = [
      { key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou." },
      { key: "other", label: "Outro motivo", customer_text: "Sentimos muito pelo imprevisto." },
    ];
    const w = await mount({ keyedReasons });
    expect(document.querySelector("[data-reason-preset]")).toBeNull();
    expect(document.querySelector("[data-reason-preview]")).toBeNull();
    // O lugar da frase já está reservado e diz o que falta (PDV2-19/PDV2-21).
    expect(dom("[data-reason-preview-pending]").text()).toContain("Escolha o motivo acima para ver a frase.");
    expect(document.body.textContent).toContain("Observação interna (opcional)");
    expect(document.body.textContent).toContain("O cliente não vê.");
    // Sem motivo escolhido, nem com observação digitada o Cancelar acende.
    await dom("[data-reason-input]").setValue("Faltou farinha");
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    const radio = document.querySelector<HTMLElement>('[data-reason-keyed] [role="radio"][aria-label="Acabou um item"]')!;
    radio.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(dom("[data-reason-preview]").text()).toContain("Um dos itens acabou.");
    expect(document.querySelector("[data-reason-preview-pending]")).toBeNull();
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeUndefined();
    await dom("[data-reason-confirm]").trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ reason: "Faltou farinha", key: "out_of_stock" }]]);
  });

  // Beta 05/11 (Gestor, Pix vencido): a tela que sabe o porquê abre com o motivo
  // marcado; Confirmar já acende e o rascunho não conta como "texto não salvo".
  it("motivo inicial: abre marcado, confirma direto e não vira rascunho", async () => {
    const keyedReasons = [
      { key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou." },
      { key: "payment_not_confirmed", label: "Pagamento não confirmado", customer_text: "Não recebemos o pagamento." },
    ];
    const w = await mount({ keyedReasons, initialKey: "payment_not_confirmed", open: false });
    await w.setProps({ open: true });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(dom("[data-reason-preview]").text()).toContain("Não recebemos o pagamento.");
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
    await dom("[data-reason-confirm]").trigger("click");
    expect(w.emitted("confirm")).toEqual([[{ reason: "", key: "payment_not_confirmed" }]]);
  });

  it("fechar com texto digitado pergunta dentro do diálogo, sem window.confirm", async () => {
    const nativeConfirm = vi.fn(() => true);
    vi.stubGlobal("confirm", nativeConfirm);
    const w = await mount();
    await dom("[data-reason-input]").setValue("Cliente desistiu");
    await dom("[data-reason-back]").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    expect(document.querySelector("[data-reason-discard]")).not.toBeNull();
    await dom("[data-reason-keep]").trigger("click");
    expect((dom("[data-reason-input]").element as HTMLTextAreaElement).value).toBe("Cliente desistiu");
    await dom("[data-reason-back]").trigger("click");
    await dom("[data-reason-discard-confirm]").trigger("click");
    expect(w.emitted("update:open")).toEqual([[false]]);
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it("ocupado: não fecha nem confirma de novo", async () => {
    const w = await mount({ busy: true });
    await dom("[data-reason-back]").trigger("click");
    await dom("[data-reason-confirm]").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    expect(w.emitted("confirm")).toBeUndefined();
  });

  it("motivo exigido sem lista: o botão apagado diz que falta escrever", async () => {
    await mount({ required: true });
    expect(dom("[data-reason-missing]").text()).toBe("Escreva o motivo para confirmar.");
  });

  // WP-G06 (laudo do Gestor, P2-29): com oito motivos em 850 px de altura o confirmar
  // ficava cortado na base do corpo, que rola. O que decide o gesto mora no rodapé.
  it("o confirmar, o Voltar e o que falta ficam no rodapé, que não rola", async () => {
    await mount({
      keyedReasons: [{ key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou." }],
    });
    const footer = document.querySelector("[data-reason-footer]")!;
    expect(footer.closest('[data-slot="footer"]')).not.toBeNull();
    expect(footer.querySelector("[data-reason-confirm]")).not.toBeNull();
    expect(footer.querySelector("[data-reason-back]")).not.toBeNull();
    expect(footer.querySelector("[data-reason-missing]")).not.toBeNull();
    // Os motivos e a frase do cliente continuam no corpo, que é o que rola.
    expect(document.querySelector('[data-slot="body"] [data-reason-keyed]')).not.toBeNull();
    expect(footer.querySelector("[data-reason-keyed]")).toBeNull();
  });

  it("a pergunta de descarte aparece no rodapé, no lugar dos botões", async () => {
    await mount();
    await dom("[data-reason-input]").setValue("Cliente desistiu");
    await dom("[data-reason-back]").trigger("click");
    const footer = document.querySelector("[data-reason-footer]")!;
    expect(footer.querySelector("[data-reason-discard]")).not.toBeNull();
    expect(footer.querySelector("[data-reason-confirm]")).toBeNull();
  });

  // P1-11: a falha da recusa aparecia num aviso atrás do diálogo aberto.
  it("a falha do gesto aparece dentro do diálogo, e o motivo escolhido fica", async () => {
    const w = await mount({ required: true });
    await dom("[data-reason-input]").setValue("Fora de área");
    expect(document.querySelector("[data-reason-error]")).toBeNull();
    await w.setProps({ error: "O Recusar não chegou. Tente de novo." });
    const alert = dom("[data-reason-error]");
    expect(alert.text()).toContain("O Recusar não chegou. Tente de novo.");
    expect(alert.attributes("data-reason-error")).toBe("action");
    expect(alert.element.closest("[data-reason-footer]")).not.toBeNull();
    expect((dom("[data-reason-input]").element as HTMLTextAreaElement).value).toBe("Fora de área");
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeUndefined();
  });

  it("a falha que aponta um campo marca o campo (dialeto detail, field, errors)", async () => {
    const keyedReasons = [{ key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou." }];
    const w = await mount({ keyedReasons, error: "Escolha um dos motivos da lista.", errorField: "key" });
    expect(dom("[data-reason-error]").attributes("data-reason-error")).toBe("key");
    expect(dom("[data-reason-keyed]").attributes("aria-invalid")).toBe("true");
    await w.setProps({ error: "", errorField: "" });
    expect(document.querySelector("[data-reason-error]")).toBeNull();
    expect(dom("[data-reason-keyed]").attributes("aria-invalid")).toBeUndefined();
  });

  it("quem chama ainda não pode deixar confirmar: o botão apaga e a linha diz por quê", async () => {
    const keyedReasons = [{ key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou." }];
    const w = await mount({ keyedReasons, blocked: "Falta ler o que acontece com o dinheiro." });
    // Primeiro o que depende de quem está na tela.
    expect(dom("[data-reason-missing]").text()).toBe("Escolha um motivo para confirmar.");
    document.querySelector<HTMLElement>('[data-reason-keyed] [role="radio"][aria-label="Acabou um item"]')!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(dom("[data-reason-missing]").text()).toBe("Falta ler o que acontece com o dinheiro.");
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeDefined();
    await dom("[data-reason-confirm]").trigger("click");
    expect(w.emitted("confirm")).toBeUndefined();
    await w.setProps({ blocked: "" });
    expect(document.querySelector("[data-reason-missing]")).toBeNull();
    expect(dom("[data-reason-confirm]").attributes("disabled")).toBeUndefined();
  });

  it("quem chama diz sobre o quê é o gesto, antes da pergunta do motivo", async () => {
    const { h } = await import("vue");
    const wrapper = await mountSuspended(OperatorReasonDialog, {
      props: { open: true, title: "Recusar o pedido W33?", description: "Escolha o motivo.", confirmLabel: "Recusar pedido" },
      slots: { summary: () => h("p", { "data-test-summary": "" }, "Ana Souza · R$ 48,00") },
      attachTo: document.body,
    });
    mounted.push(wrapper as unknown as VueWrapper);
    const summary = document.querySelector("[data-test-summary]")!;
    expect(summary.textContent).toBe("Ana Souza · R$ 48,00");
    const input = document.querySelector("[data-reason-input]")!;
    expect(summary.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
