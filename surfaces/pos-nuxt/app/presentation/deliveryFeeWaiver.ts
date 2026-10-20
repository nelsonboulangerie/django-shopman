// FRETE GRÁTIS NO BALCÃO, dito ao operador (P2-21). A loja e o PDV pedem a
// renúncia ao mesmo motor; a revisão diz qual regra renunciou (a promoção pelo
// nome, ou o valor mínimo da compra) e quanto seria a taxa sem ela. Sem isso,
// R$ 0,00 na entrega parecia endereço sem tabela, e o operador "corrigia"
// combinando um valor à mão. O frete grátis do GRUPO do cliente (reason
// "group") diz o grupo, e o mínimo quando há.
import type { POSDeliveryFeeWaiverProjection } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

type Waiver = POSDeliveryFeeWaiverProjection | null | undefined;

/** Grátis de verdade: a regra levou a taxa inteira. */
export function deliveryFeeWaivedInFull(waiver: Waiver, feeQ: number): boolean {
  return Boolean(waiver) && feeQ <= 0;
}

/** A frase de baixo, no bloco da taxa do Recebimento. "" sem renúncia. */
export function deliveryFeeWaiverNote(waiver: Waiver, feeQ: number): string {
  if (!waiver) return "";
  const base = formatBRL(waiver.base_fee_q);
  if (waiver.reason === "threshold") {
    return `Frete grátis nas compras a partir de ${formatBRL(waiver.threshold_q)} (a taxa seria ${base}).`;
  }
  if (waiver.reason === "group") {
    const minimum = waiver.threshold_q > 0 ? ` nas compras a partir de ${formatBRL(waiver.threshold_q)}` : "";
    const name = groupName(waiver);
    const who = name ? `por ser ${name}` : "do grupo do cliente";
    return `Frete grátis ${who}${minimum} (a taxa seria ${base}).`;
  }
  const promotion = promotionName(waiver);
  if (feeQ <= 0) return `Frete grátis pela ${promotion} (a taxa seria ${base}).`;
  return `A ${promotion} abate ${formatBRL(waiver.base_fee_q - feeQ)} da taxa (a taxa seria ${base}).`;
}

/** A linha curta do resumo do Pagamento, abaixo de "Taxa de entrega". "" sem renúncia. */
export function deliveryFeeWaiverShort(waiver: Waiver): string {
  if (!waiver) return "";
  if (waiver.reason === "threshold") return `Compras a partir de ${formatBRL(waiver.threshold_q)}`;
  if (waiver.reason === "group") return groupName(waiver) ? `Grupo ${groupName(waiver)}` : "Grupo do cliente";
  const name = waiver.promotion_name.trim();
  return name ? `Promoção ${name}` : "Promoção da loja";
}

function promotionName(waiver: POSDeliveryFeeWaiverProjection): string {
  const name = waiver.promotion_name.trim();
  return name ? `promoção ${name}` : "promoção da loja";
}

function groupName(waiver: POSDeliveryFeeWaiverProjection): string {
  return (waiver.group_name ?? "").trim();
}
