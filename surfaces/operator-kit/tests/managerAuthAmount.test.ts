import { describe, expect, it } from "vitest";

import { managerAuthReason, managerAuthTitle } from "../app/presentation/managerAuth";
import { formatBRL } from "../app/utils/money";

// Beta 05/11/2026 (PDV-09): a sangria de "5000" (R$ 5.000,00 lido de um R$ 50,00)
// passou pelo PIN porque o diálogo dizia só "Sai dinheiro da gaveta". O gerente
// precisa ler O VALOR que assina.
describe("managerAuth: o gerente lê o valor que assina", () => {
  it("a retirada diz o valor e o motivo", () => {
    expect(managerAuthReason({ action: "cash_out", amountQ: 500000, detail: "Sangria" })).toBe(
      `Retirada de ${formatBRL(500000)} (Sangria).`,
    );
  });

  it("troco, devolução e estorno dizem o valor", () => {
    expect(managerAuthReason({ action: "serve_change", amountQ: 10000 })).toBe(
      `Troco de ${formatBRL(10000)}. Atender abre a gaveta.`,
    );
    expect(managerAuthReason({ action: "refund_cash", amountQ: 2350 })).toBe(
      `Devolução de ${formatBRL(2350)} em dinheiro.`,
    );
    expect(managerAuthReason({ action: "card_machine_refund", amountQ: 990 })).toBe(
      `Estorno de ${formatBRL(990)} no cartão do cliente.`,
    );
  });

  it("sem valor, cai na frase fixa do ato", () => {
    expect(managerAuthReason({ action: "cash_out" })).toBe("Sai dinheiro da gaveta.");
    expect(managerAuthReason({ action: "cash_out", amountQ: 0 })).toBe("Sai dinheiro da gaveta.");
  });

  it("o motivo do servidor continua ganhando do valor", () => {
    expect(
      managerAuthReason({ action: "cash_out", amountQ: 500000, reasons: ["discount_over_threshold"], thresholdQ: 500 }),
    ).toBe(`Desconto acima de ${formatBRL(500)}.`);
  });

  it("fechar o dia com produção aberta nomeia o ato e diz o que segue aberto", () => {
    expect(managerAuthTitle("day_closing_production")).toBe("Autorizar fechar o dia");
    expect(
      managerAuthReason({ action: "day_closing_production", detail: "3 ordens de produção seguem abertas." }),
    ).toBe("3 ordens de produção seguem abertas.");
    expect(managerAuthReason({ action: "day_closing_production" })).toBe("Há produção aberta.");
  });
});

// Beta 06/11 (F5): o Gestor usava a chave do PDV ("A venda já foi fechada."),
// falsa para um pedido só autorizado. O cancelamento de pedido diz o dinheiro.
describe("managerAuth: cancelar pedido no Gestor", () => {
  it("o motivo é o efeito no dinheiro, vindo da projeção", () => {
    expect(managerAuthTitle("cancel_order")).toBe("Autorizar cancelamento");
    expect(
      managerAuthReason({ action: "cancel_order", detail: "R$ 5,10 serão estornados no cartão do cliente." }),
    ).toBe("R$ 5,10 serão estornados no cartão do cliente.");
  });

  it("sem o efeito, a frase fixa não fala em venda fechada", () => {
    expect(managerAuthReason({ action: "cancel_order" })).toBe("O pedido já foi pago.");
  });
});
