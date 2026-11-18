import { describe, expect, it } from "vitest";

import {
  noShowDialogView,
  noShowLineView,
  noShowQty,
  type NoShowLine,
  type OrderNoShowPreview,
} from "../app/presentation/orderNoShow";

// Não retirado (WP-G11): o servidor decide o destino de cada linha, o dinheiro e os
// textos. O diálogo só arruma a prévia para leitura e nunca confirma o que o
// servidor recusa.

const baguete: NoShowLine = {
  line_id: "L1",
  sku: "BAGUETE",
  name: "Baguete",
  qty: "2",
  destiny: "restock",
  destiny_label: "Volta à venda",
  reason: "",
  reason_label: "",
  value_q: 1200,
  value_display: "R$ 12,00",
};
const sanduiche: NoShowLine = {
  line_id: "L2",
  sku: "SAND",
  name: "Sanduíche de presunto",
  qty: "1",
  destiny: "loss",
  destiny_label: "Perda",
  reason: "made_to_order",
  reason_label: "Feito na hora: não volta à venda.",
  value_q: 800,
  value_display: "R$ 8,00",
};

const action = {
  ref: "no-show",
  kind: "mutation",
  label: "Encerrar como não retirado",
  priority: "danger",
  enabled: true,
  reason: "",
  href: "",
  method: "POST",
  idempotency: "required",
  payload_schema: { base_revision: "no-show-base", expected_actor_id: 1 },
  confirmation: { required: true, manager_approval: true },
} satisfies OrderNoShowPreview["action"];

function preview(overrides: Partial<OrderNoShowPreview> = {}): OrderNoShowPreview {
  return {
    ref: "WEB-1",
    allowed: true,
    block_reason: "",
    releases_at: "",
    lines: [baguete, sanduiche],
    paid_q: 2000,
    paid_display: "R$ 20,00",
    refund_q: 1200,
    refund_display: "R$ 12,00",
    retained_q: 800,
    retained_display: "R$ 8,00",
    money_sentence:
      "R$ 12,00 serão estornados ao Pix do cliente. R$ 8,00 ficam com a loja, pelo que se perdeu.",
    customer_text: "Seu pedido não foi retirado e foi encerrado.",
    managers: [],
    action,
    ...overrides,
  };
}

describe("orderNoShow", () => {
  it("pedido que volta inteiro à venda: nenhuma linha fala em perda", () => {
    const view = noShowDialogView(
      preview({
        lines: [baguete],
        money_sentence: "R$ 12,00 serão estornados ao Pix do cliente.",
      }),
    );

    expect(view.blocked).toBe(false);
    expect(view.lines).toEqual([
      { id: "L1", name: "Baguete", qty: "2", value: "R$ 12,00", destiny: "Volta à venda", tone: "neutral", why: "" },
    ]);
    expect(view.moneySentence).toBe("R$ 12,00 serão estornados ao Pix do cliente.");
    expect(view.canConfirm).toBe(true);
  });

  it("pedido que é todo perda: cada linha diz por quê, na frase do servidor", () => {
    const view = noShowDialogView(
      preview({
        lines: [sanduiche],
        money_sentence: "Nada volta ao cliente: R$ 8,00 ficam com a loja, pelo que se perdeu.",
      }),
    );

    expect(view.lines).toEqual([
      {
        id: "L2",
        name: "Sanduíche de presunto",
        qty: "1",
        value: "R$ 8,00",
        destiny: "Perda",
        tone: "warning",
        why: "Feito na hora: não volta à venda.",
      },
    ]);
    expect(view.moneySentence).toBe(
      "Nada volta ao cliente: R$ 8,00 ficam com a loja, pelo que se perdeu.",
    );
    expect(view.canConfirm).toBe(true);
  });

  it("pedido misto: cada linha com o seu destino, na ordem do servidor", () => {
    const view = noShowDialogView(preview());

    expect(view.lines.map((line) => [line.name, line.destiny, line.tone, line.why])).toEqual([
      ["Baguete", "Volta à venda", "neutral", ""],
      ["Sanduíche de presunto", "Perda", "warning", "Feito na hora: não volta à venda."],
    ]);
    expect(view.moneySentence).toBe(
      "R$ 12,00 serão estornados ao Pix do cliente. R$ 8,00 ficam com a loja, pelo que se perdeu.",
    );
    expect(view.customerText).toBe("Seu pedido não foi retirado e foi encerrado.");
  });

  it("o botão leva o rótulo da ação do servidor", () => {
    expect(noShowDialogView(preview()).confirmLabel).toBe("Encerrar como não retirado");
  });

  it("não permitido: só o motivo do servidor, sem linhas e sem confirmar", () => {
    const reason = "Pedido pago: o não retirado libera no corte do dia, às 18h.";
    const view = noShowDialogView(
      preview({
        allowed: false,
        block_reason: reason,
        action: { ...action, enabled: false, reason },
      }),
    );

    expect(view.blocked).toBe(true);
    expect(view.blockReason).toBe(reason);
    expect(view.lines).toEqual([]);
    expect(view.moneySentence).toBe("");
    expect(view.customerText).toBe("");
    expect(view.canConfirm).toBe(false);
  });

  it("gesto em andamento não confirma de novo", () => {
    expect(noShowDialogView(preview(), { busy: true }).canConfirm).toBe(false);
  });

  it("a linha que volta nunca mostra motivo de perda, mesmo que o servidor mande um", () => {
    expect(noShowLineView({ ...baguete, reason_label: "Feito na hora: não volta à venda." }).why).toBe("");
  });

  it("a quantidade se lê como no balcão: vírgula decimal, sem zero sobrando", () => {
    expect(noShowQty("2")).toBe("2");
    expect(noShowQty("10")).toBe("10");
    expect(noShowQty("0.35")).toBe("0,35");
    expect(noShowQty("2.000")).toBe("2");
    expect(noShowQty("1.500")).toBe("1,5");
  });
});
