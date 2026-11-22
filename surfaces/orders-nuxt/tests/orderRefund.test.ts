import { describe, expect, it } from "vitest";

import {
  initialRefundAmount,
  refundDialogView,
  refundToast,
  type OrderRefundPreview,
} from "../app/presentation/orderRefund";

// Estornar UM pedido (#2727, item 5): o Gerente vê os valores DESTA cobrança e de
// mais nenhuma. O diálogo não soma nada: arruma a prévia do servidor, confere o
// valor digitado contra o disponível e só acende com a segunda confirmação.

const action = {
  ref: "refund",
  kind: "mutation",
  label: "Estornar",
  priority: "danger",
  enabled: true,
  reason: "",
  href: "",
  method: "POST",
  payload_schema: { base_revision: "base", expected_actor_id: 1 },
  idempotency: "required",
  confirmation: { required: true },
};

function preview(over: Partial<OrderRefundPreview> = {}): OrderRefundPreview {
  return {
    order_ref: "WEB-1",
    method_label: "Pix",
    paid_q: 3000,
    paid_display: "R$ 30,00",
    returned_q: 500,
    returned_display: "R$ 5,00",
    available_q: 2500,
    available_display: "R$ 25,00",
    partial_allowed: true,
    blocked: false,
    block_reason: "",
    action,
    ...over,
  } as OrderRefundPreview;
}

describe("orderRefund: o diálogo", () => {
  it("abre com o disponível inteiro no campo", () => {
    expect(initialRefundAmount(preview())).toBe("25,00");
    expect(initialRefundAmount(null)).toBe("");
  });

  it("mostra o pago, o que voltou e o disponível desta cobrança", () => {
    const view = refundDialogView(preview(), { amount: "25,00", confirmed: false });
    expect(view.paidLine).toBe("Pago neste pedido: R$ 30,00 (Pix)");
    expect(view.returnedLine).toBe("Já estornado: R$ 5,00");
    expect(view.availableLine).toBe("Disponível para estorno: R$ 25,00");
  });

  it("sem estorno anterior, a linha do que voltou não existe", () => {
    const view = refundDialogView(preview({ returned_q: 0, returned_display: "" }), {
      amount: "25,00",
      confirmed: true,
    });
    expect(view.returnedLine).toBe("");
  });

  it("sem a segunda confirmação, o botão não acende", () => {
    const view = refundDialogView(preview(), { amount: "25,00", confirmed: false });
    expect(view.canConfirm).toBe(false);
    expect(view.confirmLabel).toBe("Estornar R$ 25,00");
  });

  it("parcial confirmado acende com o valor no botão", () => {
    const view = refundDialogView(preview(), { amount: "12,50", confirmed: true });
    expect(view.amountQ).toBe(1250);
    expect(view.canConfirm).toBe(true);
    expect(view.confirmLabel).toBe("Estornar R$ 12,50");
  });

  it("acima do disponível diz o limite e não confirma", () => {
    const view = refundDialogView(preview(), { amount: "25,01", confirmed: true });
    expect(view.amountError).toBe("Valor acima do disponível (R$ 25,00).");
    expect(view.canConfirm).toBe(false);
    expect(view.confirmLabel).toBe("Estornar");
  });

  it("vazio, zero ou ilegível pede o valor", () => {
    for (const amount of ["", "0,00", "doze"]) {
      const view = refundDialogView(preview(), { amount, confirmed: true });
      expect(view.amountError).toBe("Informe quanto estornar.");
      expect(view.canConfirm).toBe(false);
    }
  });

  it("bloqueado pelo servidor: só o motivo, sem valores nem botão", () => {
    const reason = "O valor desta cobrança já voltou inteiro ao cliente.";
    const view = refundDialogView(
      preview({ blocked: true, block_reason: reason, action: { ...action, enabled: false, reason } }),
      { amount: "", confirmed: true },
    );
    expect(view.blocked).toBe(true);
    expect(view.blockReason).toBe(reason);
    expect([view.paidLine, view.availableLine, view.returnedLine]).toEqual(["", "", ""]);
    expect(view.canConfirm).toBe(false);
  });

  it("ocupado, não confirma de novo", () => {
    const view = refundDialogView(preview(), { amount: "25,00", confirmed: true, busy: true });
    expect(view.canConfirm).toBe(false);
  });
});

describe("orderRefund: o aviso depois da tentativa", () => {
  it("o dinheiro voltou: diz quanto", () => {
    expect(
      refundToast({ outcome: "refunded", amount_q: 1250, refunded_q: 1250, available_q: 1250, message: "" }),
    ).toEqual({ tone: "success", text: "R$ 12,50 devolvidos ao cliente pelo mesmo meio do pagamento." });
  });

  it("não saiu: a frase do balcão que o servidor escreveu", () => {
    const message = "O Pix não aceitou o estorno. Nada foi devolvido ao cliente. Chame o suporte.";
    expect(
      refundToast({ outcome: "refused", amount_q: 1250, refunded_q: 0, available_q: 2500, message }),
    ).toEqual({ tone: "error", text: message });
  });
});
