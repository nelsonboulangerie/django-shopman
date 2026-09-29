import { describe, expect, it } from "vitest";

import {
  needsDeliveryTaxId,
  orderEditBody,
  orderEditSettlementLine,
  orderEditTitle,
  orderEditTotalLine,
} from "~/presentation/orderEdit";
import type { OrderEditOriginal, OrderEditPreview } from "~/types/preorders";

// Editar a encomenda na tela de venda (WP-E6): o corpo que sobe manda a lista
// FINAL e só o que mudou; as frases dizem, sem o operador completar sentido,
// quem paga ou quem devolve, quanto e onde.

const ENDERECO = {
  route: "Rua Sergipe", street_number: "100", neighborhood: "Centro",
  postal_code: "86010-000", city: "Londrina", state_code: "PR", complement: "",
};

function original(partial: Partial<OrderEditOriginal> = {}): OrderEditOriginal {
  return {
    items: [{ line_id: "L1", sku: "PAO", qty: 2 }],
    fulfillment_type: "pickup",
    delivery_address: "",
    delivery_address_structured: {},
    delivery_date: "2026-10-04",
    delivery_time_slot: "slot-09",
    order_notes: "sem gergelim",
    fiscal_tax_id: "",
    ...partial,
  };
}

function intent(partial: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    items: [{ line_id: "L1", sku: "PAO", name: "Pão", qty: 3, unit_price_q: 1200 }],
    fulfillment_type: "pickup",
    delivery_date: "2026-10-04",
    delivery_time_slot: "slot-09",
    order_notes: "sem gergelim",
    ...partial,
  };
}

describe("orderEditBody — a lista final e só o que mudou", () => {
  it("os itens vão sempre; observação, recebimento e data iguais não sobem", () => {
    expect(orderEditBody(intent(), original())).toEqual({ items: [{ line_id: "L1", sku: "PAO", qty: 3 }] });
  });

  it("observação e data mudadas sobem", () => {
    const body = orderEditBody(intent({ order_notes: "com gergelim", delivery_date: "2026-10-05" }), original());
    expect(body.notes).toBe("com gergelim");
    expect(body.date).toBe("2026-10-05");
    expect(body.slot).toBe("slot-09");
  });

  it("retirada que vira entrega leva endereço, exceção de taxa e CPF", () => {
    const body = orderEditBody(
      intent({
        fulfillment_type: "delivery", delivery_address: "Rua Sergipe",
        delivery_address_structured: ENDERECO, delivery_fee_override_q: 800, fiscal_tax_id: "52998224725",
      }),
      original(),
      { deliveryPaymentMethod: "cash" },
    );
    expect(body.fulfillment).toEqual({
      type: "delivery", delivery_address: "Rua Sergipe", delivery_address_structured: ENDERECO,
      delivery_fee_override_q: 800, fiscal_tax_id: "52998224725", delivery_payment_method: "cash",
    });
  });

  it("entrega com o MESMO endereço remontado pela tela não recalcula a taxa", () => {
    const body = orderEditBody(
      intent({
        fulfillment_type: "delivery",
        delivery_address_structured: { ...ENDERECO, delivery_instructions: "portão azul", formatted_address: "outra grafia" },
      }),
      original({ fulfillment_type: "delivery", delivery_address_structured: ENDERECO }),
    );
    expect(body.fulfillment).toBeUndefined();
  });

  it("o CPF do cadastro NÃO sobe calado: a entrega leva o que a caixa de salvar pediu", () => {
    const semPedir = orderEditBody(
      intent({ fulfillment_type: "delivery", delivery_address_structured: ENDERECO, customer_tax_id: "52998224725" }),
      original(),
    );
    expect(semPedir.fulfillment?.fiscal_tax_id).toBeUndefined();

    const pedido = orderEditBody(
      intent({ fulfillment_type: "delivery", delivery_address_structured: ENDERECO }),
      original(),
      { deliveryTaxId: "529.982.247-25" },
    );
    expect(pedido.fulfillment?.fiscal_tax_id).toBe("52998224725");
  });

  it("o CPF pedido numa entrega que não mudou de endereço também sobe (a encomenda ficou sem ele)", () => {
    const body = orderEditBody(
      intent({ fulfillment_type: "delivery", delivery_address_structured: ENDERECO }),
      original({ fulfillment_type: "delivery", delivery_address_structured: ENDERECO }),
      { deliveryTaxId: "52998224725" },
    );
    expect(body.fulfillment).toMatchObject({ type: "delivery", fiscal_tax_id: "52998224725" });
  });

  it("a peça pesada nova sobe com a etiqueta; a linha por unidade, sem", () => {
    const body = orderEditBody(
      intent({
        items: [
          { line_id: "L1", sku: "PAO", qty: 2 },
          { line_id: "tmp-9", sku: "QUEIJO", qty: 0.312, weighed: { entry: "label", label_q: 2805, weight_g: 312 } },
          { line_id: "tmp-10", sku: "QUEIJO", qty: 0.5, weighed: { entry: "weight", weight_g: 500 } },
        ],
      }),
      original(),
    );
    expect(body.items).toEqual([
      { line_id: "L1", sku: "PAO", qty: 2 },
      { line_id: "tmp-9", sku: "QUEIJO", qty: 0.312, weighed: { entry: "label", label_q: 2805 } },
      { line_id: "tmp-10", sku: "QUEIJO", qty: 0.5, weighed: { entry: "weight", weight_g: 500 } },
    ]);
  });

  it("entrega que vira retirada sobe só o tipo", () => {
    const body = orderEditBody(intent(), original({ fulfillment_type: "delivery", delivery_address_structured: ENDERECO }));
    expect(body.fulfillment).toEqual({ type: "pickup" });
  });
});

function preview(partial: Partial<OrderEditPreview> = {}): OrderEditPreview {
  return {
    changed: true, items_changed: true, items: [], previous_total_q: 3600, total_q: 4200, difference_q: 600,
    notes: { before: "", after: "", changed: false },
    fulfillment: { before: "pickup", after: "pickup", changed: false, delivery_address: "", delivery_fee_before_q: 0, delivery_fee_after_q: 0 },
    schedule: { changed: false, date: "", slot: "" },
    settlement: { kind: "collect", amount_q: 600, method: "" },
    balance_before_q: 0, balance_after_q: 600, requires_manager_approval: false,
    customer_note: "", ...partial,
  };
}

// O formatador da casa separa "R$" do número com espaço inseparável.
const plain = (text: string) => text.replace(/\u00a0/g, " ");

describe("frases — quem paga ou devolve, quanto e onde", () => {
  it("o título diz o que está sendo mexido", () => {
    expect(orderEditTitle("A17")).toBe("Editando a encomenda A17");
  });

  it("o total diz o novo, o de antes e a diferença com sinal", () => {
    expect(plain(orderEditTotalLine(preview()))).toBe("Novo total R$ 42,00 · era R$ 36,00 (+ R$ 6,00)");
    expect(plain(orderEditTotalLine(preview({ total_q: 3000, difference_q: -600 })))).toBe(
      "Novo total R$ 30,00 · era R$ 36,00 (− R$ 6,00)",
    );
    expect(plain(orderEditTotalLine(preview({ total_q: 3600, difference_q: 0 })))).toBe("Total R$ 36,00 (não muda)");
  });

  it("a mais: o cliente paga, e onde", () => {
    expect(plain(orderEditSettlementLine(preview()))).toBe("Cliente paga R$ 6,00 na retirada.");
    const entrega = preview({ fulfillment: { ...preview().fulfillment, after: "delivery" } });
    expect(plain(orderEditSettlementLine(entrega))).toBe("Cliente paga R$ 6,00 na entrega.");
  });

  it("a menos: pelo mesmo meio, dizendo quem faz", () => {
    const refund = (kind: OrderEditPreview["settlement"]["kind"], method: string) =>
      orderEditSettlementLine(preview({ settlement: { kind, amount_q: 600, method }, difference_q: -600 }));
    expect(plain(refund("refund_gateway", "card"))).toBe("Devolvemos R$ 6,00 no cartão do cliente, automaticamente.");
    expect(plain(refund("refund_gateway", "pix"))).toBe("Devolvemos R$ 6,00 no Pix do cliente, automaticamente.");
    expect(plain(refund("refund_cash", "cash"))).toBe(
      'Devolva R$ 6,00 em dinheiro ao cliente na retirada. Fica em "Precisa de você" até sair da gaveta.',
    );
    expect(plain(refund("refund_card_machine", "credit"))).toBe(
      'Estorne R$ 6,00 na maquininha. Fica em "Precisa de você" até o estorno ser registrado.',
    );
  });

  it("sem dinheiro a mover, diz isso — sem zero como código secreto", () => {
    expect(plain(orderEditSettlementLine(preview({ settlement: { kind: "none", amount_q: 0, method: "" }, difference_q: 0 })))).toBe(
      "O valor não muda.",
    );
  });
});

describe("o que a caixa de salvar colhe ali mesmo", () => {
  it("a recusa do CPF da entrega abre o campo do documento", () => {
    expect(needsDeliveryTaxId("delivery_tax_id_required")).toBe(true);
    expect(needsDeliveryTaxId("delivery_tax_id_invalid")).toBe(true);
    expect(needsDeliveryTaxId("delivery_address_incomplete")).toBe(false);
  });
});
