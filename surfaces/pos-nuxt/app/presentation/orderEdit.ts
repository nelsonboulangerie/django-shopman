// ENCOMENDAS · editar na tela de venda (ENCOMENDAS-PDV-PLAN, WP-E6).
//
// A régua é do servidor (`order_edit.plan`): preço, total, diferença e o destino
// dela. Aqui mora só o que a tela decide sozinha — o corpo que sobe (a lista
// FINAL e SÓ os campos que mudaram) e as frases, inequívocas, do que vai
// acontecer com o dinheiro.

import { formatBRL } from "../../../operator-kit/app/utils/money";
import type { OrderEditOriginal, OrderEditPreview } from "~/types/preorders";

export type DeliveryPaymentMethod = "cash" | "debit" | "credit";

/** O que o operador tinha em mãos para a peça pesada (etiqueta ou peso). */
export type OrderEditWeighed = { entry: "label"; label_q: number } | { entry: "weight"; weight_g: number };

export interface OrderEditBody {
  items: { line_id: string; sku: string; qty: number | string; weighed?: OrderEditWeighed }[];
  notes?: string;
  fulfillment?: {
    type: "pickup" | "delivery";
    delivery_address?: string;
    delivery_address_structured?: Record<string, unknown>;
    delivery_fee_override_q?: number;
    fiscal_tax_id?: string;
    delivery_payment_method?: DeliveryPaymentMethod;
  };
  date?: string;
  slot?: string;
}

/** O que faz de um endereço o MESMO endereço (espelho de `order_edit._ADDRESS_IDENTITY`). */
const ADDRESS_IDENTITY = ["route", "street_number", "neighborhood", "postal_code", "city", "state_code", "complement"] as const;

function addressKey(structured: unknown): string {
  const value = (structured && typeof structured === "object" ? structured : {}) as Record<string, unknown>;
  return ADDRESS_IDENTITY.map((key) => String(value[key] ?? "").trim().toLocaleLowerCase("pt-BR")).join("|");
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function digits(value: unknown): string {
  return typeof value === "string" ? value.replace(/\D/g, "") : "";
}

function weighedOf(raw: unknown): OrderEditWeighed | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Record<string, unknown>;
  if (value.entry === "label" && Number(value.label_q) > 0) return { entry: "label", label_q: Number(value.label_q) };
  if (value.entry === "weight" && Number(value.weight_g) > 0) return { entry: "weight", weight_g: Number(value.weight_g) };
  return null;
}

/**
 * O corpo de "Salvar alterações" a partir da intenção da comanda virtual.
 *
 * Os itens vão SEMPRE (lista final: é por `line_id` que o servidor reconhece o
 * que já estava e mantém o preço vendido). Observação, recebimento e data só
 * vão quando mudaram — mandar o recebimento igual faria o servidor recalcular
 * a taxa de uma entrega que ninguém mexeu.
 */
export function orderEditBody(
  intent: Record<string, unknown>,
  original: OrderEditOriginal,
  options: { deliveryPaymentMethod?: DeliveryPaymentMethod | ""; deliveryTaxId?: string } = {},
): OrderEditBody {
  const rawItems = Array.isArray(intent.items) ? (intent.items as Record<string, unknown>[]) : [];
  const body: OrderEditBody = {
    items: rawItems.map((item) => {
      // A peça pesada NOVA entra pela etiqueta (ou pelo peso), como na venda; a
      // que já estava o servidor reconhece pelo `line_id` e mantém a vendida.
      const weighed = weighedOf(item.weighed);
      return {
        line_id: String(item.line_id ?? ""),
        sku: String(item.sku ?? ""),
        qty: item.qty as number | string,
        ...(weighed ? { weighed } : {}),
      };
    }),
  };

  const notes = text(intent.order_notes);
  if (notes !== text(original.order_notes)) body.notes = notes;

  const type = intent.fulfillment_type === "delivery" ? "delivery" : "pickup";
  // O CPF da nota da entrega: o que o operador digitou em "Salvar alterações"
  // (o servidor pediu), senão o que o pedido já tem. Nunca o cadastro calado:
  // na venda o cadastro só EMPRESTA o valor inicial, e o operador vê.
  const taxId = digits(options.deliveryTaxId) || text(intent.fiscal_tax_id);
  const override = typeof intent.delivery_fee_override_q === "number" ? intent.delivery_fee_override_q : null;
  const originalOverride = typeof original.delivery_fee_override_q === "number" ? original.delivery_fee_override_q : null;
  const receivingChanged = type !== original.fulfillment_type
    || (type === "delivery" && (
      addressKey(intent.delivery_address_structured) !== addressKey(original.delivery_address_structured)
      || override !== originalOverride
      || taxId !== text(original.fiscal_tax_id)
    ));
  if (receivingChanged || options.deliveryPaymentMethod) {
    body.fulfillment = { type };
    if (type === "delivery") {
      body.fulfillment.delivery_address = text(intent.delivery_address);
      body.fulfillment.delivery_address_structured = (intent.delivery_address_structured as Record<string, unknown>) || {};
      if (override !== null) body.fulfillment.delivery_fee_override_q = override;
      if (taxId) body.fulfillment.fiscal_tax_id = taxId;
      if (options.deliveryPaymentMethod) body.fulfillment.delivery_payment_method = options.deliveryPaymentMethod;
    }
  }

  const date = text(intent.delivery_date);
  const slot = text(intent.delivery_time_slot);
  if (date !== text(original.delivery_date) || slot !== text(original.delivery_time_slot)) {
    body.date = date;
    body.slot = slot;
  }
  return body;
}

/** O cabeçalho do modo edição — inequívoco sobre o que está sendo mexido. */
export function orderEditTitle(orderRef: string): string {
  return `Editando a encomenda ${orderRef}`;
}

/** "Novo total R$ 42,00 · era R$ 36,00 (+ R$ 6,00)". */
export function orderEditTotalLine(preview: Pick<OrderEditPreview, "total_q" | "previous_total_q" | "difference_q">): string {
  if (!preview.difference_q) return `Total ${formatBRL(preview.total_q)} (não muda)`;
  const sign = preview.difference_q > 0 ? "+" : "−";
  return `Novo total ${formatBRL(preview.total_q)} · era ${formatBRL(preview.previous_total_q)} (${sign} ${formatBRL(Math.abs(preview.difference_q))})`;
}

/**
 * O que acontece com o dinheiro — uma frase, com quem faz e onde.
 *
 * Inequívoco antes de curto: "devolver" sem dizer em quê faz o operador abrir a
 * gaveta para um estorno que o Stripe já fez.
 */
export function orderEditSettlementLine(
  preview: Pick<OrderEditPreview, "settlement" | "fulfillment" | "balance_before_q" | "difference_q">,
): string {
  const { kind, amount_q: amount, method } = preview.settlement;
  const where = preview.fulfillment.after === "delivery" ? "na entrega" : "na retirada";
  switch (kind) {
    case "collect":
      return preview.balance_before_q > 0
        ? `Cliente paga ${formatBRL(amount)} ${where} (o que já faltava e a diferença).`
        : `Cliente paga ${formatBRL(amount)} ${where}.`;
    case "refund_gateway":
      return method === "pix"
        ? `Devolvemos ${formatBRL(amount)} no Pix do cliente, automaticamente.`
        : `Devolvemos ${formatBRL(amount)} no cartão do cliente, automaticamente.`;
    case "refund_cash":
      return `Devolva ${formatBRL(amount)} em dinheiro ao cliente ${where}. Fica em "Precisa de você" até sair da gaveta.`;
    case "refund_card_machine":
      return `Estorne ${formatBRL(amount)} na maquininha. Fica em "Precisa de você" até o estorno ser registrado.`;
    default:
      return preview.difference_q ? "Nada a receber nem a devolver." : "O valor não muda.";
  }
}

/** A recusa que pede ao operador como o entregador recebe o que falta. */
export function needsDeliveryPaymentMethod(code: string): boolean {
  return code === "delivery_payment_method_required";
}

/**
 * A recusa que pede o CPF/CNPJ da entrega com nota (regra de 24/09). O pedido
 * sai ali mesmo, na caixa de "Salvar alterações" — não em outra tela.
 */
export function needsDeliveryTaxId(code: string): boolean {
  return code === "delivery_tax_id_required" || code === "delivery_tax_id_invalid";
}

/**
 * Por que desconto e observação de item não aparecem na edição: o serviço de
 * edição não os grava (o que já estava mantém o preço vendido, o que entra sai
 * pelo catálogo), e gesto que não grava é tela mentindo.
 */
export const ORDER_EDIT_LINE_ADJUSTMENTS_BLOCKED =
  "Na edição da encomenda não há desconto nem observação por item: o que já estava mantém o preço vendido, e o que entra sai pelo preço do catálogo. Desconto é numa venda nova: cancele e refaça a encomenda.";

/** Por que o cliente não troca na edição: a encomenda é dele (aviso, acompanhamento). */
export const ORDER_EDIT_CUSTOMER_LOCKED =
  "O cliente da encomenda não muda na edição. Para trocar o cliente, cancele e refaça a encomenda.";

export const DELIVERY_PAYMENT_METHODS: readonly { key: DeliveryPaymentMethod; label: string }[] = [
  { key: "cash", label: "Dinheiro" },
  { key: "debit", label: "Débito" },
  { key: "credit", label: "Crédito" },
];
