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

  it("o acerto da conta na casa fora do dinheiro diz valor e forma", () => {
    expect(managerAuthTitle("settle_account")).toBe("Autorizar o acerto");
    expect(managerAuthReason({ action: "settle_account", amountQ: 15600, detail: "Pix" }))
      .toBe(`Acerto de ${formatBRL(15600)} em Pix: não passa pela gaveta.`);
    expect(managerAuthReason({ action: "settle_account" })).toBe("O acerto não passa pela gaveta.");
  });

  it("o desconto acima do teto diz QUANTO, antes do teto (beta 07/11)", () => {
    expect(managerAuthReason({ reasons: ["discount_over_threshold"], thresholdQ: 500, discountQ: 1200 }))
      .toBe(`Desconto de ${formatBRL(1200)}, acima de ${formatBRL(500)}.`);
    expect(managerAuthReason({ reasons: ["discount_over_threshold"], thresholdQ: 500, discountQ: 0 }))
      .toBe(`Desconto acima de ${formatBRL(500)}.`);
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

// Devolução depois da venda, no Gestor (WP-G12, dono 17/11/2026): o Gerente lê o
// valor e o destino do dinheiro, montados pela prévia do servidor.
describe("managerAuth: devolução no Gestor", () => {
  it("o motivo é o valor que volta e para onde", () => {
    expect(managerAuthTitle("order_return")).toBe("Autorizar a devolução");
    expect(
      managerAuthReason({ action: "order_return", detail: "R$ 12,00 serão estornados ao Pix do cliente." }),
    ).toBe("R$ 12,00 serão estornados ao Pix do cliente.");
  });

  it("sem o valor, a frase fixa do ato", () => {
    expect(managerAuthReason({ action: "order_return" })).toBe("Volta dinheiro ou produto do cliente.");
  });
});

// Não retirado, no Gestor (WP-G11): o Gerente lê o que volta ao cliente e o que
// fica com a loja, na frase que a prévia do servidor montou (`money_sentence`).
describe("managerAuth: não retirado no Gestor", () => {
  it("o ato tem nome, e o motivo é a frase do dinheiro da prévia", () => {
    expect(managerAuthTitle("order_no_show")).toBe("Autorizar encerrar como não retirado");
    const sentence = "R$ 12,00 serão estornados ao Pix do cliente. R$ 8,00 ficam com a loja, pelo que se perdeu.";
    expect(managerAuthReason({ action: "order_no_show", detail: sentence })).toBe(sentence);
  });

  it("sem a frase do dinheiro, a frase fixa do ato, sem travessão", () => {
    const fixed = managerAuthReason({ action: "order_no_show" });
    expect(fixed).toBe("O cliente não veio buscar o pedido.");
    expect(`${managerAuthTitle("order_no_show")} ${fixed}`).not.toMatch(/[—–]/);
  });
});
