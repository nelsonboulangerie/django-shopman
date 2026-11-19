import { describe, expect, it } from "vitest";

import {
  MONEY_BLOCKED,
  MONEY_LOADING,
  reasonDialogView,
  reasonErrorField,
  reasonsForOrder,
  type ReasonOrderFacts,
} from "../app/presentation/orderReason";
import type { CancelReasonProjection } from "../app/types/orders";

// WP-G06 (laudo do Gestor, P1-11): quem recusa lê qual pedido é e o que acontece com o
// dinheiro antes de confirmar, e não vê motivo que o próprio pedido desmente.

const reason = (key: string, label: string, ifood = true): CancelReasonProjection => ({
  key, label, customer_text: `${label}.`, offered_on_ifood: ifood,
});
// A lista única do backend, na ordem da tela (`shop/services/cancel_reasons.py`).
const LIST: CancelReasonProjection[] = [
  reason("out_of_stock", "Acabou um item"),
  reason("cannot_deliver", "Não dá para entregar"),
  reason("high_demand", "Muitos pedidos agora"),
  reason("duplicate_order", "Pedido repetido"),
  reason("customer_request", "O cliente pediu", false),
  reason("payment_not_confirmed", "Pagamento não confirmado", false),
  reason("store_closing", "A loja vai fechar"),
  reason("other", "Outro motivo"),
];
const keys = (list: CancelReasonProjection[]) => list.map((item) => item.key);

const order = (over: Partial<ReasonOrderFacts> = {}): ReasonOrderFacts => ({
  ref: "NB-261118-W33",
  customer_name: "Ana Souza",
  total_display: "R$ 48,00",
  fulfillment_type: "pickup",
  fulfillment_label: "Retirada",
  payment_method_label: "Pix",
  payment_status: "captured",
  payment_status_label: "Pago",
  channel_ref: "web",
  ...over,
});

describe("reasonsForOrder: o motivo que contradiz o pedido não é oferecido", () => {
  it("retirada não oferece 'Não dá para entregar'", () => {
    const shown = keys(reasonsForOrder(LIST, { order: order({ payment_status: "pending" }) }));
    expect(shown).not.toContain("cannot_deliver");
    expect(shown).toContain("payment_not_confirmed");
  });

  it("pedido pago não oferece 'Pagamento não confirmado'", () => {
    const shown = keys(reasonsForOrder(LIST, { order: order({ fulfillment_type: "delivery" }) }));
    expect(shown).not.toContain("payment_not_confirmed");
    expect(shown).toContain("cannot_deliver");
  });

  it("entrega não paga vê a lista inteira, na ordem do servidor", () => {
    const shown = reasonsForOrder(LIST, {
      order: order({ fulfillment_type: "delivery", payment_status: "pending" }),
    });
    expect(keys(shown)).toEqual(keys(LIST));
  });

  it("cartão só autorizado ainda não é dinheiro que entrou: o motivo fica", () => {
    const shown = keys(reasonsForOrder(LIST, { order: order({ payment_status: "authorized" }) }));
    expect(shown).toContain("payment_not_confirmed");
  });

  it("sem o fato do pedido, nada é escondido", () => {
    expect(keys(reasonsForOrder(LIST))).toEqual(keys(LIST));
    expect(
      keys(reasonsForOrder(LIST, { order: { ref: "NB-1", fulfillment_type: "", payment_status: "" } })),
    ).toEqual(keys(LIST));
  });

  it("o motivo que a tela trouxe marcado fica, mesmo que o pedido pareça desmentir", () => {
    const shown = keys(
      reasonsForOrder(LIST, { order: order(), initialKey: "payment_not_confirmed" }),
    );
    expect(shown).toContain("payment_not_confirmed");
  });

  it("no iFood sai o que o iFood não oferece, além do que o pedido desmente", () => {
    const shown = keys(reasonsForOrder(LIST, { order: order(), marketplace: true }));
    expect(shown).toEqual(["out_of_stock", "high_demand", "duplicate_order", "store_closing", "other"]);
  });
});

describe("reasonDialogView: o diálogo diz qual pedido e o que acontece com o dinheiro", () => {
  it("no painel: o código no título, quem pediu, quanto, e a frase do dinheiro do servidor", () => {
    const view = reasonDialogView({
      mode: "reject",
      reasons: LIST,
      order: order(),
      identify: true,
      moneyEffect: "R$ 48,00 serão estornados ao Pix do cliente.",
    });
    expect(view.title).toBe("Recusar o pedido W33?");
    expect(view.confirmLabel).toBe("Recusar pedido");
    expect(view.customer).toBe("Ana Souza");
    expect(view.total).toBe("R$ 48,00");
    expect(view.facts).toBe("Retirada · Pix · Pago");
    expect(view.money).toEqual({ state: "sentence", text: "R$ 48,00 serão estornados ao Pix do cliente." });
    expect(view.blocked).toBe("");
    expect(keys(view.reasons)).not.toContain("cannot_deliver");
    expect(keys(view.reasons)).not.toContain("payment_not_confirmed");
  });

  it("enquanto lê o dinheiro, diz que está lendo e não deixa confirmar", () => {
    const view = reasonDialogView({
      mode: "reject", reasons: LIST, order: order(), identify: true, moneyRead: "loading",
    });
    expect(view.money).toEqual({ state: "loading", text: MONEY_LOADING });
    expect(view.blocked).toBe(MONEY_BLOCKED);
  });

  it("leitura que falhou não vira silêncio: o confirmar continua apagado", () => {
    const view = reasonDialogView({
      mode: "reject", reasons: LIST, order: order(), identify: true, moneyRead: "error",
      moneyEffect: "R$ 48,00 serão estornados ao Pix do cliente.",
    });
    expect(view.money.state).toBe("error");
    expect(view.blocked).toBe(MONEY_BLOCKED);
  });

  it("sem dinheiro em jogo, não inventa frase: a linha do pagamento já diz como o pedido paga", () => {
    const view = reasonDialogView({
      mode: "reject",
      reasons: LIST,
      order: order({ payment_method_label: "Dinheiro na retirada", payment_status: "", payment_status_label: "" }),
      identify: true,
      moneyEffect: "",
    });
    expect(view.money).toEqual({ state: "none", text: "" });
    expect(view.facts).toBe("Retirada · Dinheiro na retirada");
    expect(view.blocked).toBe("");
  });

  it("no detalhe do pedido: o título de sempre, sem repetir quem é, com a frase do dinheiro", () => {
    const view = reasonDialogView({
      mode: "cancel",
      reasons: LIST,
      order: order(),
      moneyEffect: "R$ 5,10 serão estornados no cartão do cliente.",
    });
    expect(view.title).toBe("Cancelar pedido");
    expect(view.confirmLabel).toBe("Cancelar pedido");
    expect(view.customer).toBe("");
    expect(view.total).toBe("");
    expect(view.facts).toBe("");
    expect(view.money.text).toBe("R$ 5,10 serão estornados no cartão do cliente.");
    // Os motivos olham o pedido nas duas portas.
    expect(keys(view.reasons)).not.toContain("cannot_deliver");
  });

  it("sem o pedido identificado, o título não promete um código", () => {
    const view = reasonDialogView({ mode: "reject", reasons: LIST, identify: true });
    expect(view.title).toBe("Recusar pedido");
  });

  it("no iFood a instrução diz que o iFood também recebe o motivo", () => {
    const web = reasonDialogView({ mode: "reject", reasons: LIST });
    const ifood = reasonDialogView({ mode: "reject", reasons: LIST, marketplace: true });
    expect(web.description).toBe("Escolha o motivo. O cliente recebe o aviso com a frase do motivo.");
    expect(ifood.description).toBe("Escolha o motivo. O iFood e o cliente recebem o aviso com ele.");
  });

  it("nenhuma frase do diálogo usa travessão", () => {
    const views = (["loading", "ready", "error"] as const).flatMap((moneyRead) =>
      (["reject", "cancel"] as const).map((mode) =>
        reasonDialogView({ mode, reasons: LIST, order: order(), identify: true, moneyRead }),
      ),
    );
    for (const view of views) {
      const text = [view.title, view.description, view.confirmLabel, view.facts, view.money.text, view.blocked].join(" ");
      expect(text).not.toMatch(/[—–]/);
    }
  });
});

describe("reasonErrorField: o field do servidor vira o campo do diálogo", () => {
  it("reason_key é o motivo da lista; internal_note, a observação", () => {
    expect(reasonErrorField("reason_key")).toBe("key");
    expect(reasonErrorField("internal_note")).toBe("reason");
  });
  it("outro campo, ou nenhum, é falha do gesto inteiro", () => {
    expect(reasonErrorField("base_revision")).toBe("");
    expect(reasonErrorField("")).toBe("");
    expect(reasonErrorField(undefined)).toBe("");
  });
});
