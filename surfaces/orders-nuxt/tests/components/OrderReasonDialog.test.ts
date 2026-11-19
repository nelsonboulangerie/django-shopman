import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

import OperatorReasonDialog from "../../../operator-kit/app/components/OperatorReasonDialog.vue";
import OperatorScreenState from "../../../operator-kit/app/components/OperatorScreenState.vue";
import OrderReasonDialog from "../../app/components/OrderReasonDialog.vue";
import type { ReasonOrderFacts } from "../../app/presentation/orderReason";
import type { CancelReasonProjection } from "../../app/types/orders";

// O diálogo de motivo do kit (`OperatorReasonDialog`) e a peça de estado
// (`OperatorScreenState`) entram de verdade: o que se testa é o contrato do diálogo
// do Gestor sobre eles. Modal, Alert, RadioGroup, Textarea e Button vêm do harness
// (`tests/support/uiPrimitives.ts`).
const stubs = {
  NuxtIcon: { props: ["name"], template: "<i :data-icon='name' />" },
};

function mountDialog(props: Record<string, unknown> = {}, options: { attachTo?: HTMLElement } = {}) {
  return mount(OrderReasonDialog, {
    props: { marketplace: false, open: true, mode: "reject", cancelReasons: LIST, busy: false, ...props },
    global: { stubs, components: { OperatorReasonDialog, OperatorScreenState } },
    attachTo: document.body,
    ...options,
  });
}

const confirmBtn = (w: ReturnType<typeof mountDialog>, label: string) =>
  w.findAll("button").find((b) => b.text() === label)!;
const radioKeys = (w: ReturnType<typeof mountDialog>) =>
  w.findAll('[data-reason-keyed] [role="radio"]').map((r) => r.attributes("data-reason-key"));

// A lista única de motivos (dono, 07/11/2026): a mesma para recusar e cancelar.
const LIST: CancelReasonProjection[] = [
  { key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou e não conseguimos preparar o pedido completo.", offered_on_ifood: true },
  { key: "high_demand", label: "Muitos pedidos agora", customer_text: "Estamos com muitos pedidos agora e não conseguiríamos preparar o seu no horário.", offered_on_ifood: true },
  { key: "customer_request", label: "O cliente pediu", customer_text: "Conforme sua solicitação.", offered_on_ifood: false },
  { key: "payment_not_confirmed", label: "Pagamento não confirmado", customer_text: "Não recebemos a confirmação do pagamento a tempo.", offered_on_ifood: false },
  { key: "other", label: "Outro motivo", customer_text: "Sentimos muito pelo imprevisto.", offered_on_ifood: true },
];

describe("OrderReasonDialog — uma lista para recusar e cancelar", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it.each(["reject", "cancel"] as const)("%s: escolhe da lista, mostra a frase do cliente e envia a chave e a nota interna", async (mode) => {
    const w = mountDialog({ mode });
    const label = mode === "reject" ? "Recusar pedido" : "Cancelar pedido";
    expect(w.text()).toContain("O cliente recebe o aviso com a frase do motivo.");
    expect(w.text()).toContain("Observação interna (opcional)");
    expect(radioKeys(w)).toEqual(["out_of_stock", "high_demand", "customer_request", "payment_not_confirmed", "other"]);
    const btn = confirmBtn(w, label);
    expect(btn.attributes("disabled")).toBeDefined();
    await w.find("textarea").setValue("Faltou farinha");
    expect(btn.attributes("disabled")).toBeDefined();
    await w.findAll('[data-reason-keyed] [role="radio"]')[0]!.trigger("click");
    await w.vm.$nextTick();
    expect(w.find("[data-reason-preview]").text()).toContain("Um dos itens acabou");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reasonKey: "out_of_stock", internalNote: "Faltou farinha" }]);
    w.unmount();
  });

  it("no iFood esconde o que o iFood não oferece e avisa que o iFood recebe o motivo", () => {
    const w = mountDialog({ marketplace: true });
    expect(radioKeys(w)).toEqual(["out_of_stock", "high_demand", "other"]);
    expect(w.text()).toContain("O iFood e o cliente recebem o aviso com ele.");
    w.unmount();
  });

  it("Pix vencido: o cancelar abre com o motivo marcado e Confirmar já acende", async () => {
    const w = mountDialog({ mode: "cancel", open: false, initialKey: "payment_not_confirmed" });
    await w.setProps({ open: true });
    await w.vm.$nextTick();
    expect(w.find("[data-reason-preview]").text()).toContain("Não recebemos a confirmação");
    const btn = confirmBtn(w, "Cancelar pedido");
    expect(btn.attributes("disabled")).toBeUndefined();
    expect(w.emitted("dirty-change")?.at(-1)).toEqual([false]);
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reasonKey: "payment_not_confirmed", internalNote: "" }]);
    w.unmount();
  });

  it("reabrir limpa a seleção anterior", async () => {
    const w = mountDialog();
    await w.find('[data-reason-keyed] [role="radio"]').trigger("click");
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeUndefined();
    await w.setProps({ open: false });
    await w.setProps({ open: true });
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeDefined();
    w.unmount();
  });

  it("Voltar sem rascunho fecha; com nota digitada pergunta dentro do diálogo", async () => {
    window.confirm = vi.fn();
    const w = mountDialog();
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")![0]).toEqual([false]);
    await w.find("textarea").setValue("Contexto importante");
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.find("[data-reason-discard]").exists()).toBe(true);
    await confirmBtn(w, "Continuar escrevendo").trigger("click");
    expect((w.find("textarea").element as HTMLTextAreaElement).value).toBe("Contexto importante");
    expect(window.confirm).not.toHaveBeenCalled();
    w.unmount();
  });

  it("não dispensa o editor enquanto a operação está pendente", async () => {
    const w = mountDialog({ busy: true });
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")).toBeUndefined();
    w.unmount();
  });
});

// WP-G06 (laudo do Gestor, P1-11 e P2-29): recusar sem surpresa.
describe("OrderReasonDialog: qual pedido, o dinheiro e a falha, dentro do diálogo", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  const FULL: CancelReasonProjection[] = [
    { key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou.", offered_on_ifood: true },
    { key: "cannot_deliver", label: "Não dá para entregar", customer_text: "Não conseguimos fazer a entrega.", offered_on_ifood: true },
    { key: "payment_not_confirmed", label: "Pagamento não confirmado", customer_text: "Não recebemos a confirmação do pagamento a tempo.", offered_on_ifood: false },
    { key: "other", label: "Outro motivo", customer_text: "Sentimos muito pelo imprevisto.", offered_on_ifood: true },
  ];
  const order = (over: Partial<ReasonOrderFacts> = {}): ReasonOrderFacts => ({
    ref: "NB-261118-W33", customer_name: "Ana Souza", total_display: "R$ 48,00",
    fulfillment_type: "pickup", fulfillment_label: "Retirada",
    payment_method_label: "Pix", payment_status: "captured", payment_status_label: "Pago",
    channel_ref: "web", ...over,
  });
  const MONEY = "R$ 48,00 serão estornados ao Pix do cliente.";

  it("no painel diz qual pedido é e o que acontece com o dinheiro antes de confirmar", () => {
    const w = mountDialog({ cancelReasons: FULL, identify: true, order: order(), moneyEffect: MONEY });
    expect(w.get("h2").text()).toBe("Recusar o pedido W33?");
    expect(w.get("[data-reason-order-customer]").text()).toBe("Ana Souza");
    expect(w.get("[data-reason-order-total]").text()).toBe("R$ 48,00");
    expect(w.get("[data-reason-order-facts]").text()).toBe("Retirada · Pix · Pago");
    expect(w.get("[data-reason-money]").text()).toBe(MONEY);
    // O resumo vem antes da pergunta do motivo.
    const html = w.html();
    expect(html.indexOf("data-reason-money")).toBeLessThan(html.indexOf("data-reason-keyed"));
    w.unmount();
  });

  it("esconde o motivo que o pedido desmente: entrega numa retirada, pagamento num pago", () => {
    const w = mountDialog({ cancelReasons: FULL, identify: true, order: order(), moneyEffect: MONEY });
    expect(radioKeys(w)).toEqual(["out_of_stock", "other"]);
    w.unmount();
    const delivery = mountDialog({
      cancelReasons: FULL, identify: true,
      order: order({ fulfillment_type: "delivery", fulfillment_label: "Entrega", payment_status: "pending", payment_status_label: "Não pago" }),
    });
    expect(radioKeys(delivery)).toEqual(["out_of_stock", "cannot_deliver", "payment_not_confirmed", "other"]);
    delivery.unmount();
  });

  it("enquanto lê o dinheiro: diz que está lendo e o confirmar espera, mesmo com motivo", async () => {
    const w = mountDialog({ cancelReasons: FULL, identify: true, order: order(), moneyRead: "loading" });
    expect(w.get("[data-reason-money-loading]").text()).toBe("Lendo o que acontece com o dinheiro…");
    expect(w.find("[data-reason-money]").exists()).toBe(false);
    await w.find('[data-reason-keyed] [role="radio"]').trigger("click");
    const btn = confirmBtn(w, "Recusar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    expect(w.get("[data-reason-missing]").text()).toBe("Falta ler o que acontece com o dinheiro.");
    // A leitura chegou: a frase aparece, o motivo escolhido fica e o confirmar acende.
    await w.setProps({ moneyRead: "ready", moneyEffect: MONEY });
    expect(w.get("[data-reason-money]").text()).toBe(MONEY);
    expect(w.find("[data-reason-missing]").exists()).toBe(false);
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reasonKey: "out_of_stock", internalNote: "" }]);
    w.unmount();
  });

  it("leitura que falhou: diz que não leu, oferece tentar de novo e não deixa confirmar", async () => {
    const w = mountDialog({ cancelReasons: FULL, identify: true, order: order(), moneyRead: "error" });
    const failed = w.get("[data-reason-money-error]");
    expect(failed.text()).toContain("Não foi possível carregar o que acontece com o dinheiro");
    await w.find('[data-reason-keyed] [role="radio"]').trigger("click");
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeDefined();
    await failed.findAll("button").find((b) => b.text() === "Tentar de novo")!.trigger("click");
    expect(w.emitted("retry-money")).toHaveLength(1);
    w.unmount();
  });

  it("a falha da recusa aparece dentro do diálogo, com o motivo escolhido ainda marcado", async () => {
    const w = mountDialog({ cancelReasons: FULL, identify: true, order: order(), moneyEffect: MONEY });
    await w.find('[data-reason-keyed] [role="radio"]').trigger("click");
    expect(w.find("[data-reason-error]").exists()).toBe(false);
    await w.setProps({ error: "W33 continua novo: o Recusar não chegou. Tente de novo." });
    const alert = w.get("[data-reason-error]");
    expect(alert.text()).toBe("W33 continua novo: o Recusar não chegou. Tente de novo.");
    expect(alert.attributes("role")).toBe("alert");
    expect(alert.element.closest("[data-reason-footer]")).not.toBeNull();
    expect(w.find('[data-reason-keyed] [role="radio"]').attributes("aria-checked")).toBe("true");
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeUndefined();
    w.unmount();
  });

  it("o field do servidor marca o campo do diálogo (reason_key é o motivo da lista)", () => {
    const w = mountDialog({
      cancelReasons: FULL, error: "Escolha um dos motivos da lista.", errorField: "reason_key",
    });
    expect(w.get("[data-reason-error]").attributes("data-reason-error")).toBe("key");
    expect(w.get("[data-reason-keyed]").attributes("aria-invalid")).toBe("true");
    w.unmount();
  });

  it("o confirmar e o Voltar moram no rodapé, fora do corpo que rola (P2-29)", () => {
    const w = mountDialog({ cancelReasons: FULL, identify: true, order: order(), moneyEffect: MONEY });
    const footer = w.get("[data-reason-footer]");
    expect(footer.findAll("button").map((b) => b.text())).toEqual(["Voltar", "Recusar pedido"]);
    expect(footer.find("[data-reason-keyed]").exists()).toBe(false);
    w.unmount();
  });

  it("no detalhe do pedido: o título de sempre e a frase do dinheiro no corpo", () => {
    const w = mountDialog({ mode: "cancel", cancelReasons: FULL, order: order(), moneyEffect: "R$ 5,10 serão estornados no cartão do cliente." });
    expect(w.get("h2").text()).toBe("Cancelar pedido");
    expect(w.find("[data-reason-order-customer]").exists()).toBe(false);
    expect(w.get("[data-reason-money]").text()).toBe("R$ 5,10 serão estornados no cartão do cliente.");
    w.unmount();
  });

  it("sem dinheiro em jogo e sem pedido a identificar, não desenha o resumo", () => {
    const w = mountDialog();
    expect(w.find("[data-reason-order]").exists()).toBe(false);
    w.unmount();
  });
});

