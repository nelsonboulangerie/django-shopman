import { describe, expect, it } from "vitest";

import {
  clampReturnQty,
  lineRefundQ,
  returnLineHint,
  returnMoneySentence,
  returnRefundQ,
  returnSubmitItems,
  type OrderReturnPreview,
  type ReturnLine,
} from "../app/presentation/orderReturn";

// Registrar devolução (WP-G12): o diálogo soma o que o Gerente escolheu pela mesma
// regra do servidor e diz o valor e o destino do dinheiro ANTES de confirmar.

const croissant: ReturnLine = {
  line_id: "L1",
  sku: "CROIS",
  name: "Croissant",
  qty: "3",
  returned_qty: "1",
  returnable_qty: "2",
  unit_refund_q: 600,
  unit_refund_display: "R$ 6,00",
  by_weight: false,
};
const queijo: ReturnLine = {
  line_id: "L2",
  sku: "QUEIJO",
  name: "Queijo",
  qty: "0.5",
  returned_qty: "0",
  returnable_qty: "0.5",
  unit_refund_q: 8990,
  unit_refund_display: "R$ 89,90",
  by_weight: true,
};

function preview(overrides: Partial<OrderReturnPreview> = {}): OrderReturnPreview {
  return {
    ref: "P-1",
    allowed: true,
    block_reason: "",
    lines: [croissant, queijo],
    money_returns: true,
    money_destination: "serão estornados ao Pix do cliente.",
    managers: [],
    action: {} as OrderReturnPreview["action"],
    ...overrides,
  };
}

describe("orderReturn", () => {
  it("a quantidade nunca passa do que ainda pode voltar, e unidade não vira fração", () => {
    expect(clampReturnQty(croissant, 5)).toBe(2);
    expect(clampReturnQty(croissant, 1.7)).toBe(1);
    expect(clampReturnQty(croissant, -1)).toBe(0);
    expect(clampReturnQty(queijo, 0.35)).toBe(0.35);
  });

  it("o valor é o preço pago vezes a quantidade, centavo truncado como no servidor", () => {
    expect(lineRefundQ(croissant, 2)).toBe(1200);
    // 0,35 kg × R$ 89,90 = 31,465 → 3146 centavos (sem erro de ponto flutuante).
    expect(lineRefundQ(queijo, 0.35)).toBe(3146);
    expect(returnRefundQ([croissant, queijo], { L1: 2, L2: 0.35 })).toBe(4346);
  });

  it("o corpo leva só o que volta", () => {
    expect(returnSubmitItems([croissant, queijo], { L1: 2, L2: 0 })).toEqual([
      { line_id: "L1", qty: "2" },
    ]);
  });

  it("a frase do dinheiro diz quanto e para onde", () => {
    // O Intl separa "R$" do valor com espaço rígido; a frase compara com espaço comum.
    expect(returnMoneySentence(preview(), 1200).replace(/\s/g, " ")).toBe(
      "R$ 12,00 serão estornados ao Pix do cliente.",
    );
    expect(returnMoneySentence(preview(), 0)).toBe("Escolha o que volta para ver o valor.");
    expect(returnMoneySentence(preview({ money_returns: false }), 1200)).toBe(
      "Nada foi cobrado deste pedido: nenhum dinheiro volta. O produto volta ao estoque.",
    );
  });

  it("a linha diz o que ainda pode voltar e o que já voltou", () => {
    expect(returnLineHint(croissant)).toBe("Pode voltar 2 de 3 (1 já voltou)");
    expect(returnLineHint(queijo)).toBe("Pode voltar 0,5 kg de 0,5 kg");
  });
});
